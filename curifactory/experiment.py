"""This is the 'main' runnable function and CLI, which handles setting up logging,
folders, reports, and running the passed experiment.

This file contains a :code:`__name__ == "__main__"` and can be run directly.
"""

import argparse
import datetime
import importlib
import glob
import logging
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import traceback

from typing import List

from curifactory.manager import ArtifactManager
from curifactory import utils, docker

CONFIGURATION_FILE = "curifactory_config.json"


def run_experiment(  # noqa: C901 -- TODO: this does need to be broken up at some point
    experiment_name,
    parameters_list,
    overwrite_override=None,
    cache_dir_override=None,
    mngr: ArtifactManager = None,
    log: bool = False,
    log_debug: bool = False,
    dry: bool = False,
    dry_cache: bool = False,
    store_entire_run: bool = False,
    log_errors: bool = False,
    custom_name: str = None,
    build_docker: bool = False,
    build_notebook: bool = False,
    run_string: str = None,
    stage_overwrites: List[str] = None,
    args_names: List[str] = None,
    args_indices: List[str] = None,
    global_args_indices: List[str] = None,
    parallel: int = None,
    parallel_mode: bool = False,
    parallel_lock: mp.Lock = None,
    parallel_queue: mp.Queue = None,
    run_num_override: int = None,
    run_ts_override: datetime.datetime = None,
    lazy: bool = False,
    ignore_lazy: bool = False,
    notes: str = None,
):
    """The experiment entrypoint function. This executes the given experiment
    with the given parameters.

    Args:
        experiment_name (str): The name of the experiment script (without the :code:`.py`).
        parameters_list (List[str]): A list of names of parameter files (without the :code:`.py`).
        overwrite_override (bool): Whether to force overwrite on all cache data.
        cache_dir_override (str): Specify a non-default cache location. This would be used if
            running with the cache from a previous --store-full run.
        mngr (ArtifactManager): An artifact manager to use for the experiment. One will be automatically
            created if none is passed.
        log (bool): Whether to write a log file or not.
        log_debug (bool): Whether to include DEBUG level messages in the log.
        dry (bool): Setting dry to true will suppress saving any files (including logs), and will
            not update parameter stores. (It should have no effect on any files.)
        dry_cache (bool): Setting this to true only suppresses saving cache files. This is recommended
            if you're running with a cache_dir_override for some previous --store-full run, so you
            don't accidentally overwrite or add new data to the --store-full directory.
        store_entire_run (bool): Store environment info, log, output report, and all cached files in a
            run-specific folder (:code:`data/runs` by default)
        log_errors (bool): Whether to include error messages in the log output.
        custom_name (str): Instead of using the experiment name to group cached data, use this name instead.
        build_docker (bool): If true, build a docker image with all of the run cache afterwards.
        build_notebook (bool): If true, add a notebook with run info and default cells to reproduce
            after run execution.
        run_string (str): An automatically populated string representing the CLI command for the run,
            do not change this.
        stage_overwrites (List[str]): A list of string stage names that you should overwrite, this is
            useful if there are specific stages you sometimes want to recompute but the remainder of
            the data can remain cached.
        args_names (List[str]): A list of argument names to run. If this is specified only arguments
            returned from the passed parameters, with these names, will be passed to the experiment.
        args_indices (List[str]): A list of argument indices to run. If this is specified, only the
            arguments returned from the passed parameter files, indexed by the ranges specified, will
            be passed to the experiment. Note that you can specify ranges delineated with '-', e.g. '3-7'.
        global_args_indices (List[str]): A list of argument indices to run, indexing the entire set
            of parameters passed to the experiment instead of each individual paarameters file. This
            can be used to help more intelligently parallelize runs. Formatting follows the same rules
            as args_indices.
        parallel (int): How many subprocesses to split this run into. If specified, the experiment will
            be run that many times with divided up global_args_indices in order to generated cached
            data for all parameters, and then re-run a final time with all cached data combined. Note
            then that any speedup from this is based on how well and how many steps are cached.
        parallel_mode (bool): This is handled by the parallel parameter, informing a particular subproc
            run that it is being executed from a parallel run.
        parallel_lock (multiprocessing.Lock): If this function is called from a multiprocessing context, use
            this lock to help prevent files being written to and read simultaneously.
        parallel_queue (multiprocessing.Queue): If this function is called from a multiprocessing context,
            use this queue for communicating success/errors back to the main process.
        run_num_override (int): Handled in parallel mode, since parallel process experiments do not get
            run number (since manager.store is not called) the log gets stored in an incorrectly named
            file.
        run_ts_override (datetime.datetime): Handled in parallel mode, since parallel process experiments
            do not get the same timestamp if started a few seconds later, the log gets stored in an
            incorrectly named file.
        lazy (bool): If true, attempts to set all stage outputs as Lazy objects. Outputs that do not have
            a cacher specified will be given a PickleCacher. Note that objects without a cacher that do not
            handle pickle serialization correctly may cause errors.
        ignore_lazy (bool): Run the experiment disabling any lazy object caching/keeping everything in memory.
            This can save time when memory is less of an issue.
        notes (str): A git-log-like message to store in the run info for the current run. If this is an
            empty string, query the user for an input string.

    Returns:
        Whatever is returned from the experiment :code:`run()`.

    Example:
        .. code-block:: python

            from curifactory import experiment, ArtifactManager
            mngr = ArtifactManager()
            experiment.run_experiment('exp_name', ['params1', 'params2'], mngr=mngr, dry=True)
    """

    if run_string is None:
        run_string = f"experiment {experiment_name}"
        for param_file in parameters_list:
            run_string += f" -p {param_file}"
        if args_names is not None:
            for arg_name in args_names:
                run_string += f" --names {arg_name}"
        if args_indices is not None:
            for arg_index in args_indices:
                run_string += f" --indices {arg_index}"
        if stage_overwrites is not None:
            for stage_overwrite in stage_overwrites:
                run_string += f" --overwrite-stage {stage_overwrite}"
        if cache_dir_override is not None:
            run_string += f" --cache {cache_dir_override}"
        if overwrite_override:
            run_string += " --overwrite"
        if parallel is not None:
            run_string += f" --parallel {parallel}"
        if parallel_mode:
            run_string += " --parallel-mode"
        if global_args_indices is not None:
            for index_range in global_args_indices:
                run_string += f" --global-indices {index_range}"
        if store_entire_run:
            run_string += " --store-full"
        if dry:
            run_string += " --dry"
        if dry_cache:
            run_string += " --dry-cache"
        if custom_name is not None:
            run_string += f" --name {custom_name}"
        if lazy:
            run_string += " --lazy"
        if ignore_lazy:
            run_string += " --ignore-lazy"

        # TODO: remainder of flags

    # NOTE: this allows a project root /params /experiments to work, but unfortunately doesn't automagically work if you have nested folders (you need to put __init__.py in each dir)
    sys.path.append(os.getcwd())

    # distributed run check, automatically set parallel mode if we're not rank 0
    # this was added because of issues with pytorch distributed compute
    if "LOCAL_RANK" in os.environ:
        if os.getenv("LOCAL_RANK") != "0":
            parallel_mode = True
        elif "NODE_RANK" in os.environ and os.getenv("NODE_RANK") != "0":
            parallel_mode = True

    # get the experiment run notes if requested
    if notes == "":
        notes_file = "temp_run_notes_content.txt"
        # create notes template
        with open(notes_file, "w") as outfile:
            outfile.write(
                "\n\n"
                + '# Write a "git-commit-like" message to attach as notes to the experiment run. The first line will be treated as the shortform notes line.'
                + "\n# All lines starting with a '#' will be ignored."
            )

        # try to find an appropriate editor
        os.system(f"{utils.get_editor()} {notes_file}")

        # get the content
        with open(notes_file, "r") as infile:
            lines = [line for line in infile.readlines() if not line.startswith("#")]
        notes = "".join(lines).strip("\n")

        os.remove(notes_file)

    # force full store if building a docker container
    if build_docker:
        store_entire_run = True

    if mngr is None:
        mngr = ArtifactManager(
            experiment_name,
            store_entire_run=store_entire_run,
            dry=dry,
            dry_cache=dry_cache,
            custom_name=custom_name,
            run_line=run_string,
            parallel_lock=parallel_lock,
            parallel_mode=parallel_mode,
            lazy=lazy,
            ignore_lazy=ignore_lazy,
            status_override=None,
            notes=notes,
        )
        # mngr.experiment_name = experiment_name
        mngr.experiment_args_file_list = parameters_list
        if run_num_override is not None:
            mngr.experiment_run_number = run_num_override
        if run_ts_override is not None:
            mngr.run_timestamp = run_ts_override

        if stage_overwrites is not None:
            # TODO: only apply to subprocs if parallel?
            mngr.overwrite_stages = stage_overwrites

    # check for cache path override
    if cache_dir_override is not None:
        mngr.cache_path = cache_dir_override

    # resolve args indices and any specified ranges
    args_indices_resolved = []
    if args_indices is not None:
        for entry in args_indices:
            if "-" in entry:
                start = int(entry[: entry.index("-")])
                end = int(entry[entry.index("-") + 1 :])
                args_indices_resolved.extend(list(range(start, end)))
            else:
                args_indices_resolved.append(int(entry))

    # resolve global args indices and any specified ranges
    global_args_indices_resolved = []
    if global_args_indices is not None:
        for entry in global_args_indices:
            if "-" in entry:
                start = int(entry[: entry.index("-")])
                end = int(entry[entry.index("-") + 1 :])
                global_args_indices_resolved.extend(list(range(start, end)))
            else:
                global_args_indices_resolved.append(int(entry))

    # handling logging. NOTE: we do have to keep this here because of parallel considerations
    if log:
        log_name = mngr.get_reference_name()
        if parallel_mode:
            if global_args_indices is not None:
                log_name += f"_{str(global_args_indices[0])}"
            else:
                log_name += f"_p{str(os.getpid())}"
        log_path = os.path.join(mngr.logs_path, f"{log_name}.log")

        if dry:
            log_path = None

        level = logging.INFO
        if log_debug:
            level = logging.DEBUG
        utils.init_logging(log_path, level, log_errors, include_process=parallel_mode)

    logging.info("Running experiment %s" % experiment_name)

    # insert an implied parameter file that is the same as the experiment file, if no parameters were explicitly listed
    if parameters_list is None or len(parameters_list) == 0:
        logging.info(
            "No parameter files listed, assuming an implied experiment file get_params(), inserting '%s'"
            % experiment_name
        )
        parameters_list = [experiment_name]

    # load params files
    argsets = []
    for params in parameters_list:
        mngr.experiment_args[params] = []
        # TODO: if we get a ModuleNotFoundError, suggest ensuring __init__.py as appropriate and that module paths don't have '/'
        param_module_string = f"{mngr.config['params_module_name']}.{params}"
        experiment_module_string = f"{mngr.config['experiments_module_name']}.{params}"
        try:
            logging.debug("Trying to load params module '%s'" % param_module_string)
            param_module = importlib.import_module(param_module_string)
        except ModuleNotFoundError:
            # TODO:
            try:
                logging.debug(
                    "Module not found, trying '%s'" % experiment_module_string
                )
                param_module = importlib.import_module(experiment_module_string)
            except ModuleNotFoundError as e:
                logging.error(
                    "Parameter file '%s' could not be found in either experiments or parameters directory. Ensure curifactory_config.json is correct and if module subpaths are used, try including an __init__.py in each folder."
                    % params
                )
                raise e

        param_argsets = param_module.get_params()
        argsets_to_add = []

        # NOTE: we don't want to set override in parent proc on parallel runs.
        if overwrite_override and parallel is None:
            for argset in param_argsets:
                argset.overwrite = True

        # TODO: if param_argsets is not of type List, throw exception and advise
        # compute the hash of every argset and store the params
        for index, argset in enumerate(param_argsets):

            # if specific names requested, just grab those
            if args_names is not None:
                if argset.name not in args_names:
                    continue

            # if specific indices requested, just grab those
            if len(args_indices_resolved) > 0:
                if index not in args_indices_resolved:
                    continue

            argset.hash = utils.args_hash(
                argset, mngr.manager_cache_path, (not dry and not parallel_mode)
            )
            mngr.experiment_args[params].append((argset.name, argset.hash))
            # TODO: (01/24/2022) I have no idea what the point of this args_hash is...
            # it's not storing anything, and args_hash has no side-effects, so unclear
            # on why this matters.
            if store_entire_run:
                utils.args_hash(
                    argset, None, False
                )  # don't try to store because get_run_output_path does not exist yet
            argsets_to_add.append(argset)

        argsets.extend(argsets_to_add)

    if len(global_args_indices_resolved) > 0:
        argsets = [argsets[i] for i in global_args_indices_resolved]

    if not parallel_mode:
        mngr.store()

    if not parallel_mode:
        # this has to be done AFTER mngr.store, otherwise the reference name does not have the correct run number.
        logging.info(
            "Experiment run reference name is '%s'" % mngr.get_reference_name()
        )
    logging.info("Run command is '%s'" % run_string)

    # store params registry in run folder
    # TODO: is this already being done in manager get_path?
    if store_entire_run:
        for argset in argsets:
            utils.args_hash(
                argset, mngr.get_run_output_path(), (not dry and not parallel_mode)
            )

    # note that nothing is being cached or stored
    if dry:
        logging.info(
            "NOTE - running in dry mode. This log will not be saved, and no new"
            + " files will be cached. (Existing caches will still be read.)"
        )
    if store_entire_run:
        logging.info(
            "NOTE - running in full store mode. A copy of all cached objects and environment information will be stored in %s",
            mngr.get_run_output_path(),
        )

    # handle parallelism
    if parallel is not None:
        logging.info("Running experiment in parallel on %s processes..." % parallel)
        # divide up args list
        countper = int(len(argsets) / parallel)
        counts = [countper] * parallel
        remainder = len(argsets) % parallel
        index = 0
        while remainder > 0:
            counts[index] += 1
            remainder -= 1
            index += 1
            if index >= len(argsets):
                index = 0

        # get the formatted string range for each thread
        global_index_ranges = []
        start = 0
        for count in counts:
            end = start + count
            if count == 0:
                logging.warning(
                    "More processes specified than argsets, will run with fewer processes."
                )
            else:
                global_index_ranges.append([f"{start}-{end}"])
            start = end
        logging.info("Parallel arg splits: %s", str(global_index_ranges))

        processes = []
        multiprocessing_lock = mp.Lock()
        multiprocessing_queue = mp.Queue()
        for index_range in global_index_ranges:
            p = mp.Process(
                target=run_experiment,
                args=(
                    experiment_name,
                    parameters_list,
                    overwrite_override,
                    cache_dir_override,
                    None,  # mngr
                    log,
                    log_debug,
                    dry,
                    dry_cache,
                    False,  # store_entire_run
                    log_errors,
                    custom_name,
                    False,  # build_docker
                    False,  # build_notebook
                    None,  # run_string
                    stage_overwrites,
                    args_names,  # args_names
                    args_indices,  # args_indices
                    index_range,
                    None,  # parallel
                    True,  # parallel_mode
                    multiprocessing_lock,
                    multiprocessing_queue,
                    mngr.experiment_run_number,
                    mngr.run_timestamp,
                    lazy,
                    ignore_lazy,
                ),
            )
            logging.info(
                "Starting new experiment process for parameter range %s...", index_range
            )
            p.start()
            processes.append(p)

        for i, p in enumerate(processes):
            # TODO - get success/fail status
            p.join()
            run_status = multiprocessing_queue.get()
            if run_status[1] == "error":
                mngr.status = "error"
                mngr.error = run_status[2]
                mngr.error_thrown = True
                logging.info(
                    "Joined process for range '%s' with status code '%s' - %s"
                    % (global_index_ranges[i], run_status[1], run_status[2])
                )
            else:
                logging.info(
                    "Joined process for range '%s' with status code '%s'"
                    % (global_index_ranges[i], run_status[1])
                )

        logging.info(
            "All experiment processes have re-joined, continuing final combined run..."
        )

    if parallel_mode:
        logging.info(
            "Running experiment process for parameter range %s"
            % str(global_args_indices)
        )

    # run the experiment
    error_thrown = False
    experiment_module = importlib.import_module(
        f"{mngr.config['experiments_module_name']}.{experiment_name}"
    )
    try:
        results = experiment_module.run(argsets, mngr)

        # don't change status if we logged an error from a parallel process
        if not mngr.error_thrown:
            mngr.status = "complete"
    except Exception as e:
        results = None
        error_thrown = True
        logging.error(e)
        logging.error(traceback.format_exc())

        # don't change status if we logged an error from a parallel process
        if not mngr.error_thrown:
            mngr.status = "error"
            mngr.error = f"{str(e.__class__.__name__)} - {str(e)}"

    # send the results from a parallel process to the main process
    if parallel_mode and parallel_queue is not None:
        parallel_queue.put((global_args_indices[0], mngr.status, mngr.error))

    if not parallel_mode:
        mngr.store()

    if log and store_entire_run and not dry:
        # copy the logfile(s) over (when running in parallel, grab the subproc logs too)
        log_name = mngr.get_reference_name()
        log_path = f"logs/{log_name}*.log"
        for file in glob.glob(log_path):
            shutil.copy(file, mngr.get_run_output_path())
        # shutil.copyfile(
        #     log_path, os.path.join(mngr.get_run_output_path(), f"{log_name}.log")
        # )

        # TODO details file for any meta information (if it errored or not)

    if build_notebook and not dry and not parallel_mode:
        notebook_loc = os.path.join(mngr.notebooks_path, "experiments")
        try:
            os.makedirs(notebook_loc, exist_ok=True)
        # TODO: Handle exceptions better
        except:  # noqa: E722
            pass
        write_experiment_notebook(
            experiment_name,
            parameters_list,
            argsets,
            mngr,
            path=os.path.join(notebook_loc, mngr.get_reference_name()),
            use_global_cache=None,
            errored=error_thrown,
        )

    if build_docker and not dry and not parallel_mode:
        if error_thrown:
            logging.warning("The experiment threw an error - docker build skipped.")
        else:
            write_experiment_notebook(
                experiment_name,
                parameters_list,
                argsets,
                mngr,
                mngr.get_run_output_path("run_notebook"),
                use_global_cache=True,
                directory_change_back_depth=1,
                suppress_global_warning=True,
            )
            docker.build_docker(
                experiment_name,
                mngr.get_run_output_path()[:-1],
                f"{mngr.experiment_run_number}_{mngr.run_timestamp.strftime('%Y-%m-%d')}",
            )

    if not dry and not parallel_mode:
        mngr.generate_report()

    return results, mngr


def write_experiment_notebook(
    experiment_name,
    parameters_list,
    argsets,
    manager,
    path,
    directory_change_back_depth=2,
    use_global_cache=None,
    errored=False,
    suppress_global_warning=False,
):
    """Creates a jupyter notebook prepopulated with experiment info and cells to re-run
    the experiment and discover all associated data stored in record states. This function
    is run by the :code:`run_experiment()` function.

    Args:
        experiment_name (str): The name of the run experiment
        parameters_list (List[str]): List of parameter file names
        argsets (List[Args]): List of all used :code:`Args` from parameter files.
        manager (ArtifactManager): :code:`ArtifactManager` used in the experiment.
        path (str): The path to the directory to store the notebook in.
        directory_change_back_depth (int): How many directories up the notebook needs
            to be in the project root (so imports and cache paths are all correct.)
        use_global_cache (bool): Whether we're using the normal experiment cache or
            a separate specific cache folder (mostly just used to display a warning
            in the notebook.)
        errored (bool): Whether the experiment errored or nat while running, will display
            a warning in the notebook.
        suppress_global_warning (bool): Don't show a warning if :code:`use_global_cache`
            is true.
    """
    # TODO - move elsewhere?
    logging.info("Creating experiment notebook...")

    if use_global_cache is None:
        use_global_cache = not manager.store_entire_run

    output_lines = [
        "# %%",
        "'''",
        f"# {manager.experiment_name} - {manager.experiment_run_number}",
        f"\nExperiment name: **{manager.experiment_name}**  ",
        f"Experiment run number: **{manager.experiment_run_number}**  ",
        f"Run timestamp: **{manager.run_timestamp.strftime('%m/%d/%Y %H:%M:%S')}**  ",
        f"Reference: **{manager.get_reference_name()}**  ",
        f"Git commit: {manager.git_commit_hash}  ",
        f"Params files: {str(manager.experiment_args_file_list)}",
        "\n**Parameters**:",
    ]

    # output the list of parameters used and assoc hashes
    for key in manager.experiment_args:
        output_lines.append(f"* {key}")
        for name, hash in manager.experiment_args[key]:
            output_lines.append(f"\t* {name} - {hash}")

    output_lines.extend(
        [
            "---",
            "'''",
            "",
            # "# %%",
            # "'''",
        ]
    )

    # NOTE: for large argsets it makes this cell take up way too much room
    # # output detailed args for each paramset
    # for key in manager.experiment_args:
    #     for name, hash in manager.experiment_args[key]:
    #         output_lines.append(f"\n**{name} - {hash}**")
    #         output_lines.append("```")
    #         for argset in argsets:
    #             if argset.hash == hash:
    #                 argset_data = asdict(argset)
    #                 del argset_data["name"]
    #                 del argset_data["overwrite"]
    #                 del argset_data["hash"]
    #                 output_lines.append(
    #                     json.dumps(argset_data, indent=4, default=lambda x: str(x))
    #                 )
    #                 break
    #         output_lines.append("```")

    # output_lines.extend(["---", "'''", ""])

    # pathing for whether full run or not
    directory_change_back = "/".join([".."] * directory_change_back_depth)
    cache_dir_arg = f"manager_cache_path='{manager.get_run_output_path()}', cache_path='{manager.get_run_output_path()}', "
    # warn if data is potentially wrong
    if use_global_cache:
        cache_dir_arg = ""
        if not suppress_global_warning:
            output_lines.extend(
                [
                    "# %%",
                    "'''",
                    "<span style='color: orange;'><b>WARNING - </b></span>Experiment was not run with a `--store-full` flag, and so is simply using the project-wide cache rather than a specific experiment run cache. Any recent experiment runs since this notebook was created may have altered cached data."
                    "'''",
                    "",
                ]
            )

    if errored:
        output_lines.extend(
            [
                "# %%",
                "'''",
                "<span style='color: red;'><b>WARNING - </b></span>This experiment run did not complete due to an exception."
                "'''",
                "",
            ]
        )

    # imports and logger lines
    output_lines.extend(
        [
            "# %%",
            f"%cd {directory_change_back}",
            "",
            "# %%",
            "import logging",
            "from curifactory import ArtifactManager, experiment",
            "",
            "# %%",
            "logger = logging.getLogger()",
            "logger.setLevel(logging.INFO)",
            "",
            "# %%",
            f'manager = ArtifactManager("{experiment_name}", {cache_dir_arg} dry=True)',
            f'experiment.run_experiment("{experiment_name}", {str(parameters_list)}, dry=True, mngr=manager)',
            "",
            "# %%",
        ]
    )

    for i, param in enumerate(manager.records):
        output_lines.extend(
            [
                f"records{i} = manager.records[{i}]",
                f"state{i} = manager.records[{i}].state",
            ]
        )

        if manager.records[i].args is not None:
            output_lines.extend(
                [
                    f'print("state{i} - (" + records{i}.args.name + ") stages: " + str(records{i}.stages))',
                    f'print("keys: " + str(state{i}.keys()) + "\\n")',
                ]
            )
        else:
            output_lines.extend(
                [
                    f'print("state{i} - ((aggregate record)) stages: " + str(records{i}.stages))',
                    f'print("keys: " + str(state{i}.keys()) + "\\n")',
                ]
            )
        output_lines.append("")

    script_path = path + ".py"
    notebook_path = path + ".ipynb"

    output_lines = [line + "\n" for line in output_lines]

    with open(script_path, "w") as outfile:
        outfile.writelines(output_lines)

    # run ipynb-py-convert
    logging.info("Converting...")
    # utils.get_command_output(["ipynb-py-convert", script_path, notebook_path])

    cmd_array = ["ipynb-py-convert", script_path, notebook_path]
    print(*cmd_array)
    with subprocess.Popen(
        cmd_array, stderr=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1, text=True
    ) as p:
        for line in p.stdout:
            print(line, end="")  # process line here
        for line in p.stderr:
            print(line, end="")  # process line here
    logging.info("Output experiment notebook at %s", notebook_path)
    os.remove(script_path)


def regex_lister(path, regex):
    """Used by both list_experiments and list_params. This scans every file in the passed
    folder for the requested regex, and tries to import the files that have a match."""

    names = []

    if not os.path.exists(path):
        print(
            f"\t[WARNING - path: '{path}' does not exist. Double check curifactory_config.json]"
        )
        return []

    for filename in os.scandir(path):
        # iterate every python file
        if filename.path.endswith(".py"):
            with open(filename.path, "r") as infile:
                lines = infile.readlines()
                # check for a run() method
                results = [re.findall(regex, line) for line in lines]

                # remove empty arrays from findall search
                clean_results = []
                for result in results:
                    if result != []:
                        clean_results.extend(result)

                # did we find a run()?
                if len(clean_results) > 0:
                    non_pyextension_name = filename.name[:-3]

                    # see if it's valid
                    try:
                        importlib.import_module(f"{path}.{non_pyextension_name}")
                        comment = utils.get_py_opening_comment(lines)
                        if comment != "":
                            names.append(
                                non_pyextension_name
                                + " - "
                                + utils.get_py_opening_comment(lines)
                            )
                        else:
                            names.append(non_pyextension_name)
                    except Exception as e:
                        names.append(non_pyextension_name + " [ERROR - " + str(e) + "]")

    return names


def list_experiments():
    """Print out all valid experiments that have a :code:`def run()` function, including
    any top-of-file docstrings associated with each."""
    config = utils.get_configuration()

    experiment_names = regex_lister(
        config["experiments_module_name"], r"^def run\(.*\)"
    )

    return experiment_names


def list_params():
    """Print out all valid parameter files that have a :code:`def get_params()`
    function, including any top-of-file docstrings associated with each."""
    config = utils.get_configuration()

    param_names = []

    param_names.extend(
        regex_lister(config["params_module_name"], r"^def get_params\(.*\)")
    )
    param_names.extend(
        regex_lister(config["experiments_module_name"], r"^def get_params\(.*\)")
    )
    return param_names


def main():
    """'Main' command line entrypoint, parses command line flags and makes the
    appropriate :code:`run_experiment()` call."""
    parser = argparse.ArgumentParser(
        epilog="Example:\n\texperiment my_experiment -p some_params1 -p some_params2"
    )
    parser.add_argument("experiment_name")
    parser.add_argument(
        "-p",
        dest="parameters_name",
        # required=True,
        action="append",
        help="The name of a parameters python file. Does not need to include path or .py. You can specify multiple -p arguments to run all parameters",
    )
    parser.add_argument(
        "--names",
        dest="args_name",
        action="append",
        help="The name of a specific argset within one of the specified parameters files. Using this will run only the specified argset(s).",
    )
    parser.add_argument(
        "--indices",
        dest="args_index",
        action="append",
        help="A single or range of indices of argsets to use within the specified parameters files. Note that specifying this will run those indices from all specified parameters files. Specify ranges like '1-5'.",
    )
    parser.add_argument(
        "--global-indices",
        dest="global_indices",
        action="append",
        help="A single or range of indices of argsets to use out of the total list of argsets passed to the experiment.",
    )
    parser.add_argument(
        "--parallel",
        dest="parallel",
        default=None,
        help="Divide the parameters among n subprocesses in order to cache intermediate results in parallel, and then re-run in original process with cached data.",
    )
    parser.add_argument(
        "--parallel-mode",
        dest="parallel_mode",
        action="store_true",
        help="Runs an experiment and caches intermediate values but does not report or touch experiment store and parameter registry. Note that using this flag manually is not equivalent to running an experiment with the --parallel flag, as file locks don't get used when calling this manually, potentially creating race conditions.",
    )
    parser.add_argument(
        "--no-log",
        dest="no_log",
        action="store_true",
        help="Specify this flag to not store the log.",
    )
    parser.add_argument(
        "--overwrite",
        dest="overwrite_override",
        action="store_true",
        help="Overwrite current cached objects",
    )
    parser.add_argument(
        "--overwrite-stage",
        dest="overwrite_stages",
        action="append",
        help="Names of specific stages to overwrite",
    )
    parser.add_argument(
        "-s",
        "--store-full",
        dest="store_full",
        action="store_true",
        help="Store a copy of environment information and every cached object in a folder named with the experiment reference.",
    )
    parser.add_argument(
        "-c",
        "--cache",
        dest="cache_dir",
        help="Specify a different directory to use as the cache.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Log at debug level.",
    )
    parser.add_argument(
        "--dry",
        dest="dry",
        action="store_true",
        help="Do a dry run: suppresses writing any cached objects and modifying stores.",
    )
    parser.add_argument(
        "--dry-cache",
        dest="dry_cache",
        action="store_true",
        help="Do a dry cache run: this still modifies stores and runs reports but does not write anything into the cache. This is recommended when running an experiment with a cache directory from --store-full.",
    )
    parser.add_argument(
        "--log-errors",
        dest="log_errors",
        action="store_true",
        help="Include errors and stack traces in output logs. NOTE: this redirects stderr - output from libraries like tqdm will be logged as well.",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default=None,
        help="Specify a custom name to use for caching rather than the experiment name. This can be useful if multiple similar experiments can use the same cached objects. Note that this does not change the reference name.",
    )
    parser.add_argument(
        "--docker",
        dest="docker",
        action="store_true",
        help="Generates a docker image with the used cached files and a current copy of the codebase.",
    )
    parser.add_argument(
        "--notebook",
        dest="notebook",
        action="store_true",
        help="Generates a jupyter notebook to explore the results.",
    )
    parser.add_argument(
        "--lazy",
        dest="lazy",
        action="store_true",
        help="Attempts to lazy-cache all outputs from all stages. WARNING: if cachers are not specified throughout the stages, PickleCachers will be inserted. As pickle serialization does not work on some complex objects, this may fail. Specify valid cachers for all stage outputs to mitigate this.",
    )
    parser.add_argument(
        "--ignore-lazy",
        dest="ignore_lazy",
        action="store_true",
        help="Run the experiment without any lazy object caching, this can save time when memory is less of an issue.",
    )
    parser.add_argument(
        "--notes",
        nargs="?",  # this is how we allow it to be specified either as a flag or with a value
        dest="notes",
        const="",
        default=False,
        help="Associate some notes with this run. You can either directly specify a string to this flag, or leave it blank to open a notes file in your editor.",
    )
    parser.add_argument(
        "--port",
        dest="port",
        default=8080,
        help="Only used for 'experiment reports', specifies which port to run the simple server on.",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default="127.0.0.1",
        help="Only used for 'experiment reports', specifies which hostname to run the simple server on.",
    )

    # fix any missing quotes in run line
    command_parts = sys.argv[1:]

    fixed_parts = []
    for index, part in enumerate(command_parts):
        if " " in part and not part.startswith('"') and not part.endswith('"'):
            part = f'"{part}"'

            # for now we don't include the notes param, because the notes are already included in
            # the report render.
            if index > 0 and command_parts[index - 1] == "--notes":
                continue
        if part == "--notes":
            continue
        fixed_parts.append(part)

    run_string = "experiment " + " ".join(fixed_parts)

    args = parser.parse_args()
    params_list = args.parameters_name

    if args.experiment_name == "ls":

        sys.path.append(os.getcwd())
        print("EXPERIMENTS:")
        for experiment in list_experiments():
            print("\t" + experiment)
        print("\nPARAMS:")
        for param in list_params():
            print("\t" + param)
        exit()

    elif args.experiment_name == "reports":
        os.chdir("reports")
        utils.run_command(
            ["python", "-m", "http.server", str(args.port), "--bind", args.host]
        )
        os.chdir("..")
        exit()

    # todo: verify names exist
    # todo: ensure folders exist (logs)
    # todo: add cache overwrite option

    log = True
    if args.no_log:
        log = False

    parallel = None
    if args.parallel is not None:
        parallel = int(args.parallel)

    if args.notes != "" and not args.notes:
        args.notes = None

    run_experiment(
        args.experiment_name,
        params_list,
        args.overwrite_override,
        args.cache_dir,
        log=log,
        log_debug=args.verbose,
        dry=args.dry,
        dry_cache=args.dry_cache,
        store_entire_run=args.store_full,
        log_errors=args.log_errors,
        custom_name=args.name,
        build_docker=args.docker,
        build_notebook=args.notebook,
        run_string=run_string,
        stage_overwrites=args.overwrite_stages,
        args_names=args.args_name,
        args_indices=args.args_index,
        global_args_indices=args.global_indices,
        parallel=parallel,
        parallel_mode=args.parallel_mode,
        lazy=args.lazy,
        ignore_lazy=args.ignore_lazy,
        notes=args.notes,
    )


if __name__ == "__main__":
    main()
