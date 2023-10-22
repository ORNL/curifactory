"""Command line interface for curifactory and running/managing experiments.

This is effectively all of the argparse and completer logic - we want the imports
in this file to be minimal so that the startup is very fast. (Use lazy imports
where it makes sense/is feasible.)

This file contains a ``__name__ == "__main__"`` and can be run directly.
"""

import argparse

import argcomplete


def completer_experiments(**kwargs) -> list[str]:
    """Argcomplete experiment name completer. This is done by grepping
    for a ``def run(`` function."""
    # NOTE: importing "lazily" to reduce startup time of CLI
    import subprocess

    from curifactory import utils

    config = utils.get_configuration()

    experiments_path = config["experiments_module_name"].replace(".", "/")
    files = (
        subprocess.run(
            f"cd {experiments_path} && grep -rl '^def run('",
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")[:-1]
        .split("\n")
    )
    # handle if there's a ./ at the beginning (this happens with macOS's version
    # of grep)
    for index, file in enumerate(files):
        if file.startswith("./"):
            files[index] = file[2:]

    # remove .py
    files = [file[:-3] for file in files if file != ""]

    files.sort()
    return [filename.replace("/", ".") for filename in files]


def completer_params(**kwargs) -> list[str]:
    """Argcomplete parameter filenames (-p) completer. This is done by grepping
    for a ``def get_params(`` function."""
    # NOTE: importing "lazily" to reduce startup time of CLI
    import subprocess

    from curifactory import utils

    config = utils.get_configuration()
    experiments_path = config["experiments_module_name"].replace(".", "/")
    params_path = config["params_module_name"].replace(".", "/")

    experiment_files = (
        subprocess.run(
            f"cd {experiments_path} && grep -rl '^def get_params('",
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")[:-1]
        .split("\n")
    )
    # handle if there's a ./ at the beginning (this happens with macOS's version
    # of grep)
    for index, file in enumerate(experiment_files):
        if file.startswith("./"):
            experiment_files[index] = file[2:]

    # remove .py
    experiment_files = [file[:-3] for file in experiment_files if file != ""]

    param_files = (
        subprocess.run(
            f"cd {params_path} && grep -rl '^def get_params('",
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")[:-1]
        .split("\n")
    )
    # handle if there's a ./ at the beginning (this happens with macOS's version
    # of grep)
    for index, file in enumerate(param_files):
        if file.startswith("./"):
            param_files[index] = file[2:]

    # remove .py
    param_files = [file[:-3] for file in param_files if file != ""]

    files = param_files + experiment_files
    files.sort()
    return [filename.replace("/", ".") for filename in files]


def cmd_run(args):
    """``experiment [experiment_name]`` - run the specified experiment, this is the
    "main" command, NOTE: that this should eventually become ``experiment run [experiment_name]``
    when subparsers get implemented.
    """
    # NOTE: importing "lazily" to reduce startup time of CLI
    import sys

    from curifactory import experiment

    # reconstruct what the CLI would have been for this experiment if i.e. the
    # notes flag was specified, and deal with quotes
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

    log = True
    if args.no_log:
        log = False

    parallel = None
    if args.parallel is not None:
        parallel = int(args.parallel)

    if args.notes != "" and not args.notes:
        args.notes = None

    experiment.run_experiment(
        args.experiment_name,
        args.parameters_name,
        args.overwrite_override,
        args.cache_dir,
        log=log,
        log_debug=args.verbose,
        dry=args.dry,
        dry_cache=args.dry_cache,
        store_full=args.store_full,
        log_errors=args.log_errors,
        prefix=args.prefix,
        build_docker=args.docker,
        build_notebook=args.notebook,
        run_string=run_string,
        stage_overwrites=args.overwrite_stages,
        param_set_names=args.param_set_names,
        param_set_indices=args.param_set_indices,
        global_param_set_indices=args.global_indices,
        parallel=parallel,
        parallel_mode=args.parallel_mode,
        lazy=args.lazy,
        ignore_lazy=args.ignore_lazy,
        no_dag=args.no_dag,
        map_only=args.map_only,
        no_color=args.no_color,
        quiet=args.quiet,
        progress=args.progress,
        plain=args.plain,
        notes=args.notes,
        all_loggers=args.all_loggers,
    )


def cmd_ls():
    """``experiment ls`` - list out valid experiment scripts and parameter files."""
    # NOTE: importing "lazily" to reduce startup time of CLI
    import os
    import sys

    from curifactory.experiment import list_experiments, list_params

    sys.path.append(os.getcwd())
    print("EXPERIMENTS:")
    for experiment in list_experiments():
        print("\t" + experiment)
    print("\nPARAMS:")
    for param in list_params():
        print("\t" + param)


def cmd_reports(args):
    """``experiment reports`` - start up a simple python server to serve from
    the reports folder. This is to allow browsing reports through something like
    an SSH session.
    """
    # NOTE: importing "lazily" to reduce startup time of CLI
    import os

    from curifactory import reporting, utils

    if args.update:
        config = utils.get_configuration()
        utils.init_logging(None)
        reporting.update_report_index(
            config["experiments_module_name"], config["reports_path"]
        )
        return
    # TODO: (10/21/2023) we shouldn't be _required_ to be in root directory,
    # this also applies to most other commands.
    os.chdir("reports")
    utils.run_command(
        ["python", "-m", "http.server", str(args.port), "--bind", args.host]
    )
    os.chdir("..")


def main():
    """'Main' command line entrypoint, parses command line flags and makes the
    appropriate ``run_experiment()`` call as relevant."""

    parser = argparse.ArgumentParser(
        description="Run a given curifactory experiment with specified parameters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    experiment my_experiment -p some_params1 -p some_params2
    experiment my_experiment_with_params
    experiment my_experiment_with_params --overwrite

    experiment ls  # lists all available experiments and parameters
    experiment reports --port 8000 --host 0.0.0.0
""",
    )
    parser.add_argument("experiment_name").completer = completer_experiments

    parser.add_argument(
        "--notes",
        nargs="?",  # this is how we allow it to be specified either as a flag or with a value
        dest="notes",
        const="",
        default=False,
        help="Associate some notes with this run. You can either directly specify a string to this flag, or leave it blank to open a notes file in your editor.",
    )
    parser.add_argument(
        "--no-dag",
        dest="no_dag",
        action="store_true",
        help="Specifying this flag disables DAG-mode execution and prevents the pre-execution mapping of the experiment. Instead, the experiment will be run straight through using only the cache to determine if a stage needs to execute or not.",
    )

    parameters_group = parser.add_argument_group(
        "Parameterization",
        "Choose which parameter files and which parameter sets to use.",
    )
    outputs_group = parser.add_argument_group(
        "Outputs", "Control what gets created from an experiment run."
    )
    caching_group = parser.add_argument_group(
        "Caching", "Configure cache usage (re-entrancy) and lazy artifacts."
    )
    display_group = parser.add_argument_group(
        "Display", "Configure console output during experiment execution."
    )
    parallel_group = parser.add_argument_group("Parallel execution")
    reports_group = parser.add_argument_group(
        "Reports", "Arguments for use with 'experiment reports'"
    )

    # ---- PARAMETERS ----
    parameters_group.add_argument(
        "-p",
        "--params",
        dest="parameters_name",
        action="append",
        help="The name of a parameters python file. Does not need to include path or .py. You can specify multiple -p arguments to run all parameters",
    ).completer = completer_params
    parameters_group.add_argument(
        "-n",
        "--names",
        dest="param_set_names",
        action="append",
        help="The name of a specific parameter set within one of the specified parameters files. Using this will run only the specified parameter set(s).",
    )
    parameters_group.add_argument(
        "--indices",
        dest="param_set_indices",
        action="append",
        help="A single or range of indices of parameter sets to use within the specified parameters files. Note that specifying this will run those indices from all specified parameters files. Specify ranges like '1-5'.",
    )
    parameters_group.add_argument(
        "--global-indices",
        dest="global_indices",
        action="append",
        help="A single or range of indices of argsets to use out of the total list of argsets passed to the experiment.",
    )

    # ---- OUTPUTS ----
    outputs_group.add_argument(
        "--notebook",
        dest="notebook",
        action="store_true",
        help="Generates a jupyter notebook to explore the results.",
    )
    outputs_group.add_argument(
        "--docker",
        dest="docker",
        action="store_true",
        help="Generates a docker image with the used cached files and a current copy of the codebase.",
    )
    outputs_group.add_argument(
        "--no-log",
        dest="no_log",
        action="store_true",
        help="Specify this flag to not store the log.",
    )
    outputs_group.add_argument(
        "--dry",
        dest="dry",
        action="store_true",
        help="Do a dry run: suppresses writing any cached objects and modifying stores.",
    )
    outputs_group.add_argument(
        "--log-errors",
        dest="log_errors",
        action="store_true",
        help="Include errors and stack traces in output logs. NOTE: this redirects stderr - output from libraries like tqdm will be logged as well.",
    )
    outputs_group.add_argument(
        "--all-loggers",
        dest="all_loggers",
        action="store_true",
        help="Include loggers from all non-cf libraries in logging output.",
    )

    # ---- CACHING ----
    caching_group.add_argument(
        "-c",
        "--cache",
        dest="cache_dir",
        help="Specify a different directory to use as the cache.",
    )
    caching_group.add_argument(
        "-s",
        "--store-full",
        dest="store_full",
        action="store_true",
        help="Store a copy of environment information and every cached object in a folder named with the experiment reference.",
    )
    caching_group.add_argument(
        "--overwrite",
        dest="overwrite_override",
        action="store_true",
        help="Overwrite current cached objects",
    )
    caching_group.add_argument(
        "--overwrite-stage",
        dest="overwrite_stages",
        action="append",
        help="Names of specific stages to overwrite",
    )
    caching_group.add_argument(
        "--dry-cache",
        dest="dry_cache",
        action="store_true",
        help="Do a dry cache run: this still modifies stores and runs reports but does not write anything into the cache. This is recommended when running an experiment with a cache directory from --store-full.",
    )
    caching_group.add_argument(
        "--prefix",
        dest="prefix",
        default=None,
        help="Specify a custom prefix to use for caching rather than the experiment name. This can be useful if multiple similar experiments can use the same cached objects. Note that this does not change the reference name.",
    )
    caching_group.add_argument(
        "--lazy",
        dest="lazy",
        action="store_true",
        help="Attempts to lazy-cache all outputs from all stages. WARNING: if cachers are not specified throughout the stages, PickleCachers will be inserted. As pickle serialization does not work on some complex objects, this may fail. Specify valid cachers for all stage outputs to mitigate this.",
    )
    caching_group.add_argument(
        "--ignore-lazy",
        dest="ignore_lazy",
        action="store_true",
        help="Run the experiment without any lazy object caching, this can save time when memory is less of an issue.",
    )

    # ---- DISPLAY ----
    display_group.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Log at debug level.",
    )
    display_group.add_argument(
        "--map",
        dest="map_only",
        action="store_true",
        help="Specifying this _only_ runs the pre-execution record and stage mapping for the experiment, and prints out the resulting DAG information before immediately exiting. Specifying this implies --dry. You can use this flag to check which artifacts are found in cache.",
    )
    display_group.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Suppress all log output to console.",
    )
    display_group.add_argument(
        "--no-color", dest="no_color", action="store_true", help="Less fancy colors."
    )
    display_group.add_argument(
        "--progress",
        dest="progress",
        action="store_true",
        help="Display fancy progress bars! Note that this uses rich live and can break existing tqdm progress bars and other things.",
    )
    display_group.add_argument(
        "--plain",
        dest="plain",
        action="store_true",
        help="Print normal logging rather than rich colored logs. This will output the exact same text printed into the file log.",
    )

    # ---- PARALLEL ----
    parallel_group.add_argument(
        "--parallel",
        dest="parallel",
        default=None,
        help="Divide the parameters among n subprocesses in order to cache intermediate results in parallel, and then re-run in original process with cached data.",
    )
    parallel_group.add_argument(
        "--parallel-safe",
        dest="parallel_mode",
        action="store_true",
        help="Runs an experiment and caches intermediate values but does not report or touch experiment store and parameter registry. Note that using this flag manually is not equivalent to running an experiment with the --parallel flag, as file locks don't get used when calling this manually, potentially creating race conditions.",
    )

    # ---- REPORTS ----
    reports_group.add_argument(
        "--port",
        dest="port",
        default=8080,
        help="Only used for 'experiment reports', specifies which port to run the simple server on.",
    )
    reports_group.add_argument(
        "--host",
        dest="host",
        default="127.0.0.1",
        help="Only used for 'experiment reports', specifies which hostname to run the simple server on.",
    )
    reports_group.add_argument(
        "--update",
        dest="update",
        action="store_true",
        help="Only used for 'experiment reports', updates the report index with all exisiting reports in the reports file. This is to handle if you pull in reports from other machines.",
    )
    argcomplete.autocomplete(parser, always_complete_options=False)

    args = parser.parse_args()

    if args.experiment_name == "ls":
        cmd_ls()
        return

    elif args.experiment_name == "reports":
        cmd_reports(args)
        return

    cmd_run(args)

    # TODO: verify names exist
    # TODO: ensure folders exist (logs)


if __name__ == "__main__":
    main()
