"""Contains the relevant classes for experiment state, namely the artifact manager and
record classes, as well as experiment store/parameter store management."""

from datetime import datetime
import json
import logging
import multiprocessing as mp
import os
from socket import gethostname
import sys
from typing import List, Dict

from curifactory import utils, reporting
from curifactory.reporting import Reportable
from curifactory.record import Record
from curifactory.store import ManagerStore


class ArtifactManager:
    """This class manages the records, metadata, and options for an experiment run.

    Every experiment run needs an instance of this.

    Args:
        experiment_name (str): The name of the experiment. This is used as a prefix for
            most relevant information and affects caching paths. If a manager is being
            used primarily from jupyter notebooks, you could for instance set this to
            be the name of the notebook.
        store_entire_run (bool): Store/copy environment info, log, output report, and
            all cached files in a run-specific folder (this is a --store-full run.)
        dry (bool): Setting dry to true will suppress saving any files (including logs), and will
            not update parameter stores. (It should have no effect on any files.)
        dry_cache (bool): Setting this to true only suppresses saving cache files. This is recommended
            if you're running with a cache_dir_override for some previous --store-full run, so you
            don't accidentally overwrite or add new data to the --store-full directory.
        custom_name (str): Instead of using the experiment name to group cached data, use
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
        store_entire_run: bool = False,
        dry: bool = False,
        dry_cache: bool = False,
        custom_name: str = None,
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
        self.pip_freeze = ""
        """The output from a :code:`pip freeze` command."""
        self.conda_env = ""
        """The output from a conda env command (:code:`conda env export --from-history`)."""
        self.os = ""
        """The name of the current OS running curifactory."""
        self.hostname = gethostname()
        """The hostname of the machine this experiment ran on."""

        self.custom_name = custom_name
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
        self.store_entire_run: bool = store_entire_run
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
        """For live session managers where you don't wish to set overwrite on individual args, you can universely set the manager to overwrite by changing this flag to True."""  # TODO: (01/27/2022) take this into consideration in staging.

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
            if self.store_entire_run:
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
            if self.store_entire_run:
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

    def get_all_argsets(self) -> List:
        """This is important to get argsets that aren't obtained through parameter files, e.g. in an interactive session."""
        master_list = []
        found_hashes = []
        for record in self.records:
            if record.args is not None:
                if record.args.hash not in found_hashes:
                    master_list.append(record.args)
                    found_hashes.append(record.args.hash)

        return master_list

    def get_grouped_reportables(self) -> Dict[str, List[Reportable]]:
        """Returns a dictionary of reportable groups, each group containing the list of reportables."""
        grouped_reportables = {}
        for reportable in self.reportables:
            if reportable.group is None:
                continue
            if reportable.group not in grouped_reportables:
                grouped_reportables[reportable.group] = []
            grouped_reportables[reportable.group].append(reportable)
        return grouped_reportables

    def get_ungrouped_reportables(self) -> List[Reportable]:
        """Returns the list of reportables that have no group."""
        non_grouped_reportables = []
        for reportable in self.reportables:
            if reportable.group is None:
                non_grouped_reportables.append(reportable)
        return non_grouped_reportables

    def get_path(
        self,
        obj_name: str,
        record: Record,
        output: bool = False,
        base_path: str = None,
        aggregate_records: List[Record] = None,
    ) -> str:
        """Get an appropriate full path/filename for a given object name and record.

        This is used by the cachers, it automatically handles generating a filename
        using appropriate experiment name prefixing etc.

        Args:
            obj_name (str): The name to associate with the object as the last part of the filename.
            record (Record): The record that this object is associated with. (Used to get experiment name, args hash
                and so on.)
            output (bool): Set this to true if the path needs to be based in a --store-full run folder.
            base_path (str): If a specific path override is needed, pass it in here. (Otherwise the
                manager's cache_path is used.)
            aggregate_records (List[Record]): If a list of records is passed (not none), prefix the
                path filename with the hash of arg hashes of all the passed records. This is used for
                paths for cached objects of aggregate stages.

        Returns:
            A string filepath that an object can be written to.
        """
        args_hash = "None"

        # compute args hash if necessary
        if record.args is not None:
            record.args.hash = utils.args_hash(
                record.args, self.manager_cache_path, self.dry
            )
            args_hash = record.args.hash
            object_path = f"{self.experiment_name}_{record.args.hash}_{self.current_stage_name}_{obj_name}"

            if self.store_entire_run:
                utils.args_hash(record.args, self.get_run_output_path(), self.dry)

        # set the hash to the hashed version of all args hashes from passed records if applicable
        if aggregate_records is not None:
            args_hash = utils.add_args_combo_hash(
                record, aggregate_records, self.manager_cache_path, not self.dry
            )  # TODO: uses not here, but doesn't up above?
            if self.store_entire_run:
                utils.add_args_combo_hash(
                    record, aggregate_records, self.get_run_output_path(), not self.dry
                )

        object_path = (
            f"{self._get_name()}_{args_hash}_{self.current_stage_name}_{obj_name}"
        )

        if output:
            return os.path.join(self.get_run_output_path(), object_path)
        elif base_path is not None:
            return os.path.join(base_path, object_path)
        else:
            return os.path.join(self.cache_path, object_path)

    def get_str_timestamp(self) -> str:
        """Convert the manager's run timestamp into a string representation."""
        return self.run_timestamp.strftime(utils.TIMESTAMP_FORMAT)

    def _get_name(self) -> str:
        if self.custom_name is None:
            return self.experiment_name
        return self.custom_name

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
        if self.store_entire_run:
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

    def get_reportable_groups(self) -> List[str]:
        groups = []
        for reportable in self.reportables:
            if reportable.group not in groups:
                groups.append(reportable.group)
        return groups
