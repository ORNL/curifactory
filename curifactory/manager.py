"""Contains the relevant classes for experiment state, namely the artifact manager and
record classes, as well as experiment store/parameter store management."""

import json
import logging
import multiprocessing as mp
import os
import sys
from datetime import datetime
from socket import gethostname

from curifactory import reporting, utils
from curifactory.record import Record
from curifactory.reporting import Reportable
from curifactory.store import ManagerStore


class ArtifactManager:
    """This class manages the records, metadata, and options for an experiment run.

    Every experiment run needs an instance of this.

    Args:
        experiment_name (str): The name of the experiment. This is used as a prefix for
            most relevant information and affects caching paths. If a manager is being
            used primarily from jupyter notebooks, you could for instance set this to
            be the name of the notebook.
        store_full (bool): Store/copy environment info, log, output report, and
            all cached files in a run-specific folder (this is a --store-full run.)
        dry (bool): Setting dry to true will suppress saving any files (including logs), and will
            not update parameter stores. (It should have no effect on any files.)
        dry_cache (bool): Setting this to true only suppresses saving cache files. This is recommended
            if you're running with a cache_dir_override for some previous --store-full run, so you
            don't accidentally overwrite or add new data to the --store-full directory.
        prefix (str): Instead of using the experiment name to group cached data, use
            this name instead.
        run_line (str): The CLI command used to run the current experiment.
        parallel_lock (multiprocessing.Lock): If this function is called from a multiprocessing
            context, use this lock to help prevent files being written to and read simultaneously.
        parallel_mode (bool): This is handled by the parallel parameter, informing a particular subproc
            run that it is being executed from a parallel run.
        lazy (bool): If true, attempts to set all stage outputs as Lazy objects. Outputs that do not have
            a cacher specified will be given a PickleCacher. Note that objects without a cacher tht do not
            handle pickle serialization correctly may cause errors.
        ignore_lazy (bool): Run the experiment disabling any lazy object caching/keeping everything in memory.
            This can save time when memory is less of an issue.
        notes (str): A git-log-like message to store in the run info for the current run. If this is an
            empty string, query the user for an input string.
        manager_cache_path (str): The path where the parameter registry and experiment
            store data are kept.
        cache_path (str): The path where all intermediate data is cached.
        runs_path (str): The path where full experiment stores (run with :code:`--store-full`)
            are kept.
        logs_path (str): The path where run logs get stored.
        notebooks_path (str): The path where run notebooks are placed.
        reports_path (str): The path where experiment run reports are saved.
        report_css_path (str): The path to a CSS file to copy into each report directory.
        status_override (str): This variable is 'LIVE' by default, but is overriden by the experiment script.
            'LIVE' indicates that this manager is being run from a non-experiment script or interactive terminal.
        suppress_live_log (bool): If true, on live/interactive runs don't automatically spawn a logger.
        live_log_debug (bool): If true, spawn live logger with the DEBUG level.
    """

    def __init__(
        self,
        experiment_name: str = None,
        store_full: bool = False,
        dry: bool = False,
        dry_cache: bool = False,
        prefix: str = None,
        run_line: str = "",
        parallel_lock: mp.Lock = None,
        parallel_mode: bool = False,
        lazy: bool = False,
        ignore_lazy: bool = False,
        notes: str = None,
        manager_cache_path: str = None,
        cache_path: str = None,
        runs_path: str = None,
        logs_path: str = None,
        notebooks_path: str = None,
        reports_path: str = None,
        report_css_path: str = None,
        status_override: str = "LIVE",
        suppress_live_log: bool = False,
        live_log_debug: bool = False,
    ):
        self.current_stage_name = ""
        """The name of the stage currently executing."""
        self.stage_active = False
        """Flag indicating whether a stage is actively running or not, used to
        detect if a stage has directly called another stage. (Technically not
        disallowed but a big no-no/prohibits any DAG features.)"""

        self.experiment_name = experiment_name
        """The name of the experiment and/or the prefix used for caching."""
        self.run_timestamp = datetime.now()
        """The datetime timestamp for when the manager is initialized (and usually
        also when the experiment starts running.)"""
        self.experiment_run_number = 0
        """The run counter for experiments with the given name."""
        self.experiment_args_file_list = []
        """The list of parameter file names to be used in the experiment."""
        self.experiment_args = {}
        """A dictionary keyed by parameter file names, where the values are arrays of the name of the
        argset and arg hashes for all argsets from that parameter file. (See the 'args' field in the
        metadata blocks in ManagerStore.)"""
        self.git_commit_hash = ""
        """The current commit hash if a git repo is in use."""
        self.git_workdir_dirty = False
        """Whether there are uncommited changes in the git repo or not."""
        self.pip_freeze = ""
        """The output from a :code:`pip freeze` command."""
        self.conda_env = ""
        """The output from a conda env command (:code:`conda env export --from-history`)."""
        self.os = ""
        """The name of the current OS running curifactory."""
        self.hostname = gethostname()
        """The hostname of the machine this experiment ran on."""

        self.prefix = prefix
        """If specified, the name to use for grouping cached data instead of the experiment name."""
        self.notes = notes
        """A notes associated with a session/run to output into the report etc."""

        self.manager_cache_path = manager_cache_path
        """The path where the parameter registry and experiment store data are kept."""
        self.cache_path = cache_path
        """The path where all intermediate data is cached."""
        self.runs_path = runs_path
        """The path where full experiment stores (run with :code:`--store-full`) are kept."""
        self.logs_path = logs_path
        """The path where run logs get stored."""
        self.notebooks_path = notebooks_path
        """The path where run notebooks are placed."""
        self.reports_path = reports_path
        """The path where experiment run reports are saved."""
        self.report_css_path = report_css_path
        """The path to a CSS file to copy into each report directory."""

        self.config = {}
        """The manager configuration loaded from the curifactory config file if present."""

        self.records = []
        """The list of records currently managed by this manager."""
        self.store_full: bool = store_full
        """Flag for whether to store/copy environment info, log, output report, and
        all cached files in a run-specific folder."""
        self.dry: bool = dry
        """Flag for whether to suppress all file outputs (cached files, logs, registries etc.)"""
        self.dry_cache: bool = dry_cache
        """Flag for whether to suppress only writing cached files."""
        self.artifacts = []
        """The list of :code:`ArtifactRepresentation` instances for all artifacts stored in all
        record states."""
        self.reportables = []
        """The list of all reportables reported from all records."""

        self.stored = False
        """A flag keeping track of if the experiment :code:`store.json` has been updated with this run
        or not."""
        self.run_info = None
        """The metadata block associated with this manager from the :code:`ManagerStore`."""
        self.run_line = run_line
        """The CLI command used to run the current experiment."""
        self.reproduction_line = ""
        """The CLI command to replicate the experiment this manager is for."""
        self.interactive = False
        """Indicates if this manager was spawned with LIVE status in an interactive environment (e.g. a python
        terminal or Jupyter notebook.)"""

        # TODO: shouldn't we allow this to directly be passed into the constructor?
        self.overwrite_stages = []
        """The list of individual stages for which to ignore the cache."""
        self.overwrite = False
        """For live session managers where you don't wish to set overwrite on individual args, you can universely set the manager to overwrite by changing this flag to True."""

        self.error_thrown = False
        """A flag indicating whether an error was thrown by the experiment."""
        self.status = "incomplete" if status_override is None else status_override
        """The current status of the experiment: 'incomplete', 'complete', 'error', or 'LIVE' if run from a
        notebook, interactive terminal, or non-experiment script."""
        self.error = None
        """The exception class and error string, if one was thrown."""

        self.parallel_lock = parallel_lock
        """If this function is called from a multiprocessing context, use this lock to help
        prevent files being written to and read simultaneously."""
        self.parallel_mode = parallel_mode
        """A flag indicating whether this manager is in a "subproc" run or not. Do not set this manually."""

        self.lazy = lazy
        """If true, attempts to set all stage outputs as Lazy objects. Outputs that do not have.
        a cacher specified will be given a PickleCacher. Note that objects without a cacher tht do not
        handle pickle serialization correctly may cause errors."""
        self.ignore_lazy = ignore_lazy
        """Run the experiment disabling any lazy object caching/keeping everything in memory.
        This can save time when memory is less of an issue."""

        self.live_report_path_generated = False
        """A flag indicting if the default report's graphs/reportables folders exist, this helps prevent live displays from breaking if multiple display functions called."""
        self.live_report_paths = None

        self.map_mode = False
        """If we're in map mode, don't actually execute any stages, we're only
        recording the 'DAG' (really just the set of stages associated with each
        record)"""
        self.map: list[Record] = None

        self.map_progress = None
        self.map_progress_overall_task_id = None

        self._load_config()

        if not self.dry and not self.dry_cache:
            if not os.path.exists(self.cache_path):
                os.makedirs(self.cache_path)
            if not os.path.exists(self.runs_path):
                os.makedirs(self.runs_path)

        if not self.dry:
            # TODO: (01/25/2022) maybe keep reports path check for when we're actually generating the report
            if not os.path.exists(self.reports_path):
                os.makedirs(self.reports_path)
            if not os.path.exists(self.logs_path):
                os.makedirs(self.logs_path)

        # handle populating alternate run line
        if self.status == "LIVE":
            if hasattr(sys, "ps1"):
                self.run_line = "(Interactive environment)"
                self.interactive = True
            else:
                self.run_line = " ".join(sys.argv)

        if not self.parallel_mode:
            # NOTE: by this point we don't technically have things like experiment args, but subsequent store calls will appropriately update it (see update_run in store.py) The reason this is important is so that the log init below has the correct run number etc.
            self.store()

        # start logging if from a live environment (otherwise experiment script handles this)
        if self.status == "LIVE" and not suppress_live_log and not self.parallel_mode:
            log_name = self.get_reference_name()
            log_path = os.path.join(self.logs_path, f"{log_name}.log")
            level = logging.DEBUG if live_log_debug else logging.INFO
            if self.dry:
                log_path = None
            utils.init_logging(log_path, level, False)

    def map_records(self):
        """Run through every record currently stored and grab the stage and
        stage i/o list and store it. Then clean the records."""
        self.map = []

        for record in self.records:
            mapped_record = Record(self, record.args, hide=True)
            mapped_record.stages = record.stages
            mapped_record.stage_inputs = record.stage_inputs
            mapped_record.stage_outputs = record.stage_outputs
            mapped_record.is_aggregate = record.is_aggregate
            mapped_record.combo_hash = record.combo_hash
            self.map.append(mapped_record)
            # TODO: input_records?

        self.records.clear()

    # update_type can either be "start" or "continue"
    # start type means "stage start", not record start, though we could check if
    # it hasn't been started yet.
    def update_map_progress(self, record, update_type: str = ""):
        if self.map_progress is not None and not self.map_mode:
            # self.map_progress.update(self.map_progress.task_ids[0], advance=1)
            # find appropriate record
            # TODO: use aggregate (or non) hash as the way to find the correct
            # record.
            taskid = -1
            name = record.args.name if record.args is not None else "None"
            record_hash = record.get_hash()
            record_index = -1
            for i, map_record in enumerate(self.map):
                map_record_hash = map_record.get_hash()
                # map_name = (
                #     map_record.args.name if map_record.args is not None else "None"
                # )
                if map_record_hash == record_hash:
                    taskid = map_record.taskid
                    record_index = i

            map_task = None
            for task in self.map_progress.tasks:
                if task.id == taskid:
                    map_task = task

            # continue is called when a stage/aggregate is complete and about to
            # return
            if update_type == "continue":
                self.map_progress.update(taskid, advance=1, visible=True, name="")
                if map_task.completed == map_task.total:
                    self.map_progress.update(
                        self.map_progress_overall_task_id, advance=1
                    )
                    self.map_progress.update(self.map_progress_overall_task_id, name="")

            # start gets called at the beginning of a stage or aggregate
            # decorator
            elif update_type == "start":
                self.map_progress.update(
                    taskid, visible=True, name=f"Stage {record.stages[-1]}"
                )
                if not map_task.started:
                    self.map_progress.start_task(taskid)
                self.map_progress.update(
                    self.map_progress_overall_task_id,
                    name=f"Record {record_index} ({name})",
                )

    def _load_config(self):
        """Populate any non-pre-existing path values with config values."""
        self.config = utils.get_configuration()
        if self.manager_cache_path is None:
            self.manager_cache_path = self.config["manager_cache_path"]
        if self.cache_path is None:
            self.cache_path = self.config["cache_path"]
        if self.runs_path is None:
            self.runs_path = self.config["runs_path"]
        if self.logs_path is None:
            self.logs_path = self.config["logs_path"]
        if self.notebooks_path is None:
            self.notebooks_path = self.config["notebooks_path"]
        if self.reports_path is None:
            self.reports_path = self.config["reports_path"]
        if self.report_css_path is None:
            self.report_css_path = self.config["report_css_path"]

    def store(self):
        """Update the ManagerStore with this manager's run metadata."""
        if self.dry:
            return
        if self.stored:
            # update
            store = ManagerStore(self.manager_cache_path)
            self.run_info = store.update_run(self)
            if self.store_full:
                # update relevant run_info too with new_run
                if self.run_info is not None:
                    with open(
                        self.get_run_output_path("run_info.json"), "w"
                    ) as outfile:
                        json.dump(self.run_info, outfile, indent=4)
            return
        else:
            store = ManagerStore(self.manager_cache_path)
            self.run_info = store.add_run(self)
            self.stored = True
            if self.store_full:
                self.write_run_env_output()

    def write_run_env_output(self):
        """Write all environment metadata to a run folder for a --store-full run."""
        self.pip_freeze = utils.get_pip_freeze()
        self.conda_env = utils.get_conda_env()
        self.os = utils.get_os()

        with open(
            self.get_run_output_path("requirements.txt"), "w", newline=""
        ) as outfile:
            outfile.write(self.pip_freeze)

        if self.conda_env != "":
            with open(
                self.get_run_output_path("environment.yml"), "w", newline=""
            ) as outfile:
                outfile.write(self.conda_env)

        with open(self.get_run_output_path("environment_meta.txt"), "w") as outfile:
            outfile.write(self.os)

        if self.run_info is not None:
            with open(self.get_run_output_path("run_info.json"), "w") as outfile:
                json.dump(self.run_info, outfile, indent=4)

    def get_all_argsets(self) -> list:
        """This is important to get argsets that aren't obtained through parameter files, e.g. in an interactive session."""
        master_list = []
        found_hashes = []
        for record in self.records:
            if record.args is not None:
                if record.args.hash not in found_hashes:
                    master_list.append(record.args)
                    found_hashes.append(record.args.hash)

        return master_list

    def get_grouped_reportables(self) -> dict[str, list[Reportable]]:
        """Returns a dictionary of reportable groups, each group containing the list of reportables."""
        grouped_reportables = {}
        for reportable in self.reportables:
            if reportable.group is None:
                continue
            if reportable.group not in grouped_reportables:
                grouped_reportables[reportable.group] = []
            grouped_reportables[reportable.group].append(reportable)
        return grouped_reportables

    def get_ungrouped_reportables(self) -> list[Reportable]:
        """Returns the list of reportables that have no group."""
        non_grouped_reportables = []
        for reportable in self.reportables:
            if reportable.group is None:
                non_grouped_reportables.append(reportable)
        return non_grouped_reportables

    def get_artifact_path(
        self,
        obj_name: str,
        record: Record,
        subdir: str = None,
        prefix: str = None,
        stage_name: str = None,
        store: bool = False,
    ) -> str:
        """Get a record-appropriate full path/filename for a given object name and record.

        This is used by the cachers, it automatically handles generating a filename
        using appropriate experiment name prefixing etc. **NOTE:** This function sets the record's args hash if it is None, or if an aggregate stage is involved.

        The output path will follow this convention: ``[base path]/[prefix]_[parameterset hash]_[stage name]_[artifact name]``,
        where ``base path`` is determined based on the value of ``store`` and ``subdir``.

        Args:
            obj_name (str): The name to associate with the object as the last part of the filename.
            record (Record): The record that this object is associated with. (Used to get experiment name, args hash
                and so on.)
            subdir (str): An optional string of one or more nested subdirectories to prepend to the artifact filepath.
                This can be used if you want to subdivide cache and run artifacts into logical subsets, e.g. similar to
                https://towardsdatascience.com/the-importance-of-layered-thinking-in-data-engineering-a09f685edc71.
            prefix (str): An optional alternative prefix to the experiment-wide prefix (either the experiment name or
                custom-specified experiment prefix). This can be used if you want a cached object to work easier across
                multiple experiments, rather than being experiment specific. WARNING: use with caution, cross-experiment
                caching can mess with provenance.
            stage_name (str): The stage that produced an artifact. If not supplied, uses
                the currently executing stage name.
            store (bool): Set this to true if the path needs to go into a --store-full run folder.

        Returns:
            A string filepath that an object can be written to.
        """
        # TODO: provide some examples in the docstring
        args_hash = record.get_hash()
        if prefix is None:
            prefix = self._get_name()

        if stage_name is None:
            stage_name = self.current_stage_name

        # NOTE: at some point if we have better parallel handling in cf, we'll probably
        # want "current_stage_name" to be on the record level rather than the manager level.
        object_path = f"{prefix}_{args_hash}_{stage_name}_{obj_name}"

        base_path = self.cache_path
        if store:
            base_path = os.path.join(self.get_run_output_path(), "artifacts")

        # if specific subdirectories are requested, those go at the _end_ of the base path.
        # e.g. 'data/cache/my/sub/directories/[object_filepath]'
        if subdir is not None:
            base_path = os.path.join(base_path, subdir)

        # TODO: (3/21/2023) unsure if always making the path is correct, may need
        # to add a parameter for this
        os.makedirs(base_path, exist_ok=True)
        return os.path.join(base_path, object_path)

    def get_str_timestamp(self) -> str:
        """Convert the manager's run timestamp into a string representation."""
        return self.run_timestamp.strftime(utils.TIMESTAMP_FORMAT)

    def _get_name(self) -> str:
        if self.prefix is None:
            return self.experiment_name
        return self.prefix

    def get_reference_name(self) -> str:
        """Get the reference name of this run in the experiment registry.

        The format for this name is [experiment_name]_[run_number]_[timestamp]."""
        return f"{self.experiment_name}_{self.experiment_run_number}_{self.get_str_timestamp()}"

    def get_run_output_path(self, obj_name: str = None):
        """Get the path for a --store-full run folder for this manager. Similar to get_path, but
        with an always assumed output=True.

        Returns:
            A string filepath pointing to the runs folder with an optional object name attached at
            end. (Returns only the folder path if None is passed.)
        """
        output_path = os.path.join(self.runs_path, self.get_reference_name())
        return_path = output_path
        # have to be careful ordering of where we put stuff into output_path, because makedirs will
        # make _everything_ a dir, even filename a dir too, so only include if a '/' found in obj_name
        if obj_name is not None:
            return_path = os.path.join(return_path, obj_name)
            if "/" in obj_name:
                additional_sub_folders = obj_name[: obj_name.rindex("/")]
                output_path = os.path.join(output_path, additional_sub_folders)
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        return return_path

    def lock(self):
        """Necessary to avoid file collisions when run in parallel mode."""
        if self.parallel_lock is not None:
            self.parallel_lock.acquire()

    def unlock(self):
        """Necessary to avoid file collisions when run in parallel mode."""
        if self.parallel_lock is not None:
            self.parallel_lock.release()

    def generate_report(self):
        """Output report files to a run-specific report folder, the reports/_latest, and the store-full folder if applicable."""
        if self.dry:
            return
        logging.info("Generating report...")

        self.store()

        reporting.run_report(self, self.reports_path, "_latest", self.report_css_path)
        self.live_report_paths = reporting.run_report(
            self, self.reports_path, self.get_reference_name(), self.report_css_path
        )
        self.live_report_path_generated = True
        if self.store_full:
            reporting.run_report(
                self, self.get_run_output_path(), "report", self.report_css_path
            )
        reporting.update_report_index(
            self.config["experiments_module_name"], self.reports_path
        )

    def display_info(self):
        """Returns an IPython HTML display object with the report info block. This is mostly only useful for making displays in a Juptyer notebook."""
        try:
            from IPython.display import HTML
        except ModuleNotFoundError:
            return "Unable to import IPython."
        self.store()

        return HTML("".join(reporting.render_report_info_block(self)))

    def _reportable_display_prep(self):
        from IPython.display import HTML  # TODO: better error handling for this?

        self.store()

        if not self.live_report_path_generated:
            self.live_report_paths = reporting.prepare_report_path(
                self.reports_path, self.get_reference_name()
            )
            self.live_report_path_generated = True
        return HTML

    def display_all_reportables(self):
        """Displays (via html) all produced reportables.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()
        folder_path, graphs_path, reportables_path = self.live_report_paths

        html = reporting.render_report_all_reportables(
            self,
            reportables_path,
            override_display_path=os.path.join("/", "files", reportables_path),
            notebook=True,
        )

        return HTML("".join(html))

    def display_record_reportables(self, record: Record):
        """Displays (via html) all reportables produced within the passed record.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()
        folder_path, graphs_path, reportables_path = self.live_report_paths

        html_lines = []
        for reportable in self.reportables:
            if reportable.record == record:
                html_lines.extend(
                    reporting.render_reportable(
                        reportable,
                        self,
                        reportables_path,
                        override_display_path=os.path.join(
                            "/", "files", reportables_path
                        ),
                        notebook=True,
                    )
                )

        return HTML("".join(html_lines))

    def display_group_reportables(self, group_name: str):
        """Displays (via html) all reportables in the passed group.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()
        folder_path, graphs_path, reportables_path = self.live_report_paths

        html_lines = []
        for reportable in self.reportables:
            if reportable.group == group_name:
                html_lines.extend(
                    reporting.render_reportable(
                        reportable,
                        self,
                        reportables_path,
                        override_display_path=os.path.join(
                            "/", "files", reportables_path
                        ),
                        notebook=True,
                    )
                )

        return HTML("".join(html_lines))

    def display_stage_reportables(self, stage_name: str):
        """Displays (via html) all reportables produced by the given stage.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()
        folder_path, graphs_path, reportables_path = self.live_report_paths

        html_lines = []
        for reportable in self.reportables:
            if reportable.stage == stage_name:
                html_lines.extend(
                    reporting.render_reportable(
                        reportable,
                        self,
                        reportables_path,
                        override_display_path=os.path.join(
                            "/", "files", reportables_path
                        ),
                        notebook=True,
                    )
                )

        return HTML("".join(html_lines))

    def display_reportable(self, reportable: Reportable):
        """Displays (via html) the rendered passed reportable.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()
        folder_path, graphs_path, reportables_path = self.live_report_paths

        html = reporting.render_reportable(
            reportable,
            self,
            reportables_path,
            override_display_path=os.path.join("/", "files", reportables_path),
            notebook=True,
        )

        return HTML("".join(html))

    def display_stage_graph(self):
        """Displays (via html) the graphviz SVG map of the records and the stages they were run through.

        Note:
            This only works within an IPython context.
        """
        HTML = self._reportable_display_prep()

        html = reporting.render_graph(reporting.map_full_svg(self))
        return HTML("".join(html))

    def get_reportable_groups(self) -> list[str]:
        groups = []
        for reportable in self.reportables:
            if reportable.group not in groups:
                groups.append(reportable.group)
        return groups
