# https://stackoverflow.com/questions/37367331/is-it-possible-to-use-argparse-to-capture-an-arbitrary-set-of-optional-arguments
# https://stackoverflow.com/questions/14950964/overriding-default-argparse-h-behaviour
# https://stackoverflow.com/questions/4042452/display-help-message-with-python-argparse-when-script-is-called-without-any-argu

import argparse
import logging
from dataclasses import MISSING, fields

import argcomplete

import curifactory.experimental as cf

CONSOLE = None


def completer_pipeline(**kwargs) -> list[str]:
    # manager = cf.get_manager()
    # prefix = kwargs["prefix"]
    # manager.import_pipelines_from_module(prefix)
    # return manager.pipeline_keys_matching(prefix)
    return []


def get_console():
    global CONSOLE
    if CONSOLE is not None:
        return CONSOLE

    from rich.console import Console

    CONSOLE = Console()
    return CONSOLE


def print_load_failures(debug=False):
    manager = cf.get_manager()
    if len(manager.failed_imports) == 0:
        return

    console = get_console()
    out_str = ""
    for failed_module in manager.failed_imports:
        exception, stack = manager.failed_imports[failed_module]
        out_str += f'[red]Pipeline module "{failed_module}" failed on import: [/red]{type(exception).__name__}: {exception}\n'
        # out_str += f"Pipeline module \"{failed_module}\" failed on import: {type(exception).__name__}: {exception}\n"
        if debug:
            out_str += stack + "\n"
        # out_str += "\n".join(stack)
    console.print(out_str)


def open_duckdb_repl():
    # https://docs.python.org/3/library/code.html
    # https://stackoverflow.com/questions/1395913/how-to-drop-into-repl-read-eval-print-loop-from-python-code

    help_str = """[blue]==== Entering python REPL ====[/blue]
Modules:[purple]
    duckdb
    curifactory.experimental as cf
[/purple]------------------------------
Local objects:[green]
    db: duckdb connection to curifactory store.db
    manager: current curifactory manager
[/green]------------------------------
helpful manager functions:[magenta]
    manager.runs: property that gets cf_run table as a df
    manager.get_pipeline("name_or_ref"): load the specified pipeline from module or previous run refs
    manager.get_pipeline_names(): list all found pipelines for use with get_pipeline
[/magenta]------------------------------
Curifactory duckdb tables:[yellow]
    cf_run
    cf_stage
    cf_artifact
    cf_run_stage
    cf_stage_input
    cf_run_artifact
[/yellow]------------------------------"""
    console = get_console()
    console.print(help_str)

    # try to load into ipython first if possible
    try:
        import IPython
        from traitlets.config import Config

        c = Config()
        c.InteractiveShellApp.exec_lines = [
            "import duckdb",
            "import curifactory.experimental as cf",
        ]
        manager = cf.get_manager()
        db = manager.db_connection()
        IPython.embed(config=c, colors="neutral")
    except:  # noqa: E722
        import code

        scope = globals()
        manager = cf.get_manager()
        db = manager.db_connection()
        scope["manager"] = manager
        scope["db"] = db
        iconsole = code.InteractiveConsole(locals=scope)
        iconsole.runsource("import duckdb")
        iconsole.runsource("import curifactory.experimental as cf")
        iconsole.interact()


def cmd_run(parsed, parser, run_parser):  # noqa: C901
    pipeline = None

    manager = cf.get_manager()
    manager.load_default_pipeline_imports()
    if parsed.pipeline is not None:
        manager.import_pipelines_from_module(parsed.pipeline)
    print_load_failures(parsed.debug)

    search = parsed.pipeline
    resolved = manager.resolve_reference(search)
    # print(manager.imported_module_names)
    # print(resolved)

    if "pipeline_instance" in resolved:
        pipeline = resolved["pipeline_instance"]
        base_class = False
    elif "reference_instance" in resolved:
        pipeline = resolved["reference_instance"]
        base_class = False
    elif "pipeline_class" in resolved:
        pipeline = resolved["pipeline_class"]
        base_class = True

    if pipeline is not None:
        name = pipeline.name if not base_class else pipeline.__name__
        pipeline_parameter_group = run_parser.add_argument_group(
            f"{name} parameters", pipeline.__doc__
        )

        # # TODO: https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
        def list_converter(string):
            # print("I was called with", string)
            resolved = manager.resolve_reference(string)
            # print(resolved)
            if "pipeline_instance" in resolved:
                # print("FOUND!")
                return resolved["pipeline_instance"]

            return string

        # add arguments for the pipeline to the parser
        names = []
        for field in fields(pipeline):
            if field.name in ["name", "outputs"]:
                continue
            names.append(field.name)

            default = None
            if not base_class:
                default = getattr(pipeline, field.name)
            elif field.default_factory != MISSING:
                default = field.default_factory()

            action = "store"
            # print(field.name, field.type, field.type.__name__)
            if field.type.__name__ == "list":
                # https://stackoverflow.com/questions/47077329/python-get-type-of-typing-list
                action = "append"

            cleaned_type = field.type
            if field.type.__name__ == "list":
                cleaned_type = list_converter

            pipeline_parameter_group.add_argument(
                f"--{field.name}",
                type=cleaned_type,
                dest=field.name,
                action=action,
                help=f"Default: {default}",
            )

        parsed_better, _ = parser.parse_known_args()

        new_args = {}
        for name in names:
            if vars(parsed_better)[name] is not None:
                new_args[name] = vars(parsed_better)[name]

        if len(new_args) > 0:
            if base_class:
                # print(new_args)
                pipeline = pipeline(pipeline.__name__, **new_args)
            else:
                pipeline = pipeline.modify(**new_args)

    if parsed.show_help:
        run_parser.print_help()
        if pipeline is None:
            print(f"Pipelines matching '{search}':")
            for exp_key, exp_val in resolved["pipeline_instance_list"].items():
                print(f"{exp_key} ({exp_val.name})")
            print("---")
            print(f"Pipeline classes matching '{search}':")
            for exp_class in resolved["pipeline_class_list"]:
                print(exp_class.__name__)
        return

    if pipeline is not None:
        # print(pipeline)
        manager.init_root_logging()
        if parsed.debug:
            manager.logger.setLevel(logging.DEBUG)

        # handle replacements
        if parsed.replace is not None:
            for replace_req in parsed.replace:
                if "=" not in replace_req:
                    raise SyntaxError("Please use '-r source_artifact=dest_artifact'")
                parts = replace_req.split("=")
                source = parts[0]
                dest = parts[1]
                source_resolved = manager.resolve_reference(source)
                if "artifact" not in source_resolved:
                    print(f"Couldn't find an artifact for {source}")
                    exit()
                source = source_resolved["artifact"]
                dest_resolved = manager.resolve_reference(dest)
                if "artifact" not in dest_resolved:
                    print(f"Couldn't find an artifact for {dest}")
                    exit()
                dest = dest_resolved["artifact"]

                manager.logger.debug(
                    f"Replacing {source.contextualized_name} with {dest.contextualized_name}"
                )
                # source.replace(dest.copy())  # not actually sure why this breaks
                source.replace(dest)
            pipeline.consolidate_shared_artifacts()

        # handle overwrites
        if parsed.overwrite is not None:
            for overwrite_req in parsed.overwrite:
                art_resolved = manager.resolve_reference(overwrite_req)
                if (
                    "artifact" not in art_resolved
                    and "artifact_list" not in art_resolved
                ):
                    print(f"COULD NOT FIND {overwrite_req}.")
                    exit()
                else:
                    if "artifact" in art_resolved:
                        art_resolved["artifact"].overwrite = True
                        manager.logger.debug(
                            f"Setting overwrite on art_{art_resolved['artifact'].name}"
                        )
                    else:
                        for artifact in art_resolved["artifact_list"]:
                            manager.logger.debug(
                                f"Setting overwrite on art_{artifact.name}"
                            )
                            artifact.ovewrite = True
        if parsed.overwrite_all:
            manager.logger.info("Setting overwrite on all artifacts")
            for artifact in pipeline.artifacts:
                artifact.overwrite = True

        if "artifact" not in resolved and "artifact_list" not in resolved:
            # print(pipeline)
            pipeline.run()
            pipeline.report(save=True)
        else:
            if "artifact" in resolved:
                name = resolved["artifact"].name
                manager.logger.debug(f"Attempting to get Artifact '{name}'")
                resolved["artifact"].get()
            elif "artifact_list" in resolved:
                manager.logger.debug(
                    f"Attempting to get Artifacts {[artifact.name for artifact in resolved['artifact_list']]}"
                )
                for artifact in resolved["artifact_list"]:
                    artifact.get()
                artifact.context.report(save=True)


def cmd_config(parsed, parser, conf_parser):
    import json

    manager = cf.get_manager()
    print(json.dumps(manager.config, indent=4))


def cmd_db(parsed, parser, db_parser):
    manager = cf.get_manager()
    if parsed.sub_command == "version":
        with manager.db_connection() as db:
            print(f"Manager DB version: {cf.db_tables.get_schema_version(db)}")
        print(f"Curifactory DB version: {cf.db_tables.SCHEMA_VERSION}")
    elif parsed.sub_command == "verify":
        with manager.db_connection() as db:
            print(cf.db_tables.verify_schemas(db))
    elif parsed.sub_command == "migrate":
        manager.init_root_logging()
        with manager.db_connection() as db:
            print(cf.db_tables.run_migrations(db))
    elif parsed.sub_command == "fix":
        with manager.db_connection() as db:
            for fix in cf.db_tables.FIXES:
                if getattr(parsed, fix):
                    print(f"Running {fix}")
                    cf.db_tables.FIXES[fix](db)
    else:
        open_duckdb_repl()


def cmd_map(parsed, parser, map_parser):  # noqa: C901
    manager = cf.get_manager()
    manager.load_default_pipeline_imports()
    manager.import_pipelines_from_module(parsed.pipeline)

    search = parsed.pipeline
    resolved = manager.resolve_reference(search)

    pipeline = None
    if "pipeline_instance" in resolved:
        pipeline = resolved["pipeline_instance"]
    elif "reference_instance" in resolved:
        pipeline = resolved["reference_instance"]

    if pipeline is not None:

        # handle replacements
        if parsed.replace is not None:
            for replace_req in parsed.replace:
                if "=" not in replace_req:
                    raise SyntaxError("Please use '-r source_artifact=dest_artifact'")
                parts = replace_req.split("=")
                source = parts[0]
                dest = parts[1]
                source_resolved = manager.resolve_reference(source)
                if "artifact" not in source_resolved:
                    print(f"Couldn't find an artifact for {source}")
                    exit()
                source = source_resolved["artifact"]
                dest_resolved = manager.resolve_reference(dest)
                if "artifact" not in dest_resolved:
                    print(f"Couldn't find an artifact for {dest}")
                    exit()
                dest = dest_resolved["artifact"]

                manager.logger.debug(
                    f"Replacing {source.contextualized_name} with {dest.contextualized_name}"
                )
                # source.replace(dest.copy())  # not actually sure why this breaks
                source.replace(dest)
            pipeline.consolidate_shared_artifacts()

        # handle overwrites
        if parsed.overwrite is not None:
            for overwrite_req in parsed.overwrite:
                art_resolved = manager.resolve_reference(overwrite_req)
                if (
                    "artifact" not in art_resolved
                    and "artifact_list" not in art_resolved
                ):
                    print(f"COULD NOT FIND {overwrite_req}.")
                    exit()
                else:
                    if "artifact" in art_resolved:
                        art_resolved["artifact"].overwrite = True
                        manager.logger.debug(
                            f"Setting overwrite on art_{art_resolved['artifact'].name}"
                        )
                    else:
                        for artifact in art_resolved["artifact_list"]:
                            manager.logger.debug(
                                f"Setting overwrite on art_{artifact.name}"
                            )
                            artifact.ovewrite = True

        if parsed.overwrite_all:
            manager.logger.debug("Setting overwrite on all artifacts")
            for artifact in pipeline.artifacts:
                artifact.overwrite = True

        if "artifact" not in resolved and "artifact_list" not in resolved:
            mapped = pipeline.map()
        elif "artifact" in resolved:
            mapped = resolved["artifact"].map()
        elif "artifact_list" in resolved:
            mapped = None
            for artifact in resolved["artifact_list"]:
                mapped = artifact.map(mapped)
        # print(resolved)

    artifact_counts = {
        "to_compute": 0,
        "use_cache": 0,
        "skipped": 0,
        "found_in_cache": 0,
    }
    stage_counts = {"to_compute": 0, "skipped": 0}
    for artifact in mapped["artifacts"]:
        if artifact.map_status in [cf.COMPUTE, cf.OVERWRITE]:
            artifact_counts["to_compute"] += 1
        elif artifact.map_status == cf.USE_CACHE:
            artifact_counts["use_cache"] += 1
        elif artifact.map_status == cf.SKIP:
            artifact_counts["skipped"] += 1
        if artifact.cache_status == cf.IN_CACHE:
            artifact_counts["found_in_cache"] += 1

    for stage in mapped["stages"]:
        if stage.map_status == cf.COMPUTE:
            stage_counts["to_compute"] += 1
        elif stage.map_status == cf.SKIP:
            stage_counts["skipped"] += 1

    console = get_console()
    map_str = ""
    # TODO: this is unfortunately kind of slow.
    for stage in mapped["stages"]:
        stage_color = ""
        stage_str = f"---- Stage {stage.context.name}.{stage.name} ".ljust(55)
        stage_str += cf.status(stage.map_status).ljust(10)
        if stage.map_status == cf.SKIP:
            stage_color = "[grey35]"
        else:
            stage_color = "[bright_yellow]"

        map_str += f"{stage_color}{stage_str}[/]\n"

        for artifact in mapped["artifacts"]:
            if artifact.compute == stage:
                if artifact.map_status == cf.USE_CACHE:
                    color = "magenta"
                elif artifact.map_status == cf.SKIP:
                    color = "grey35"
                elif artifact.map_status == cf.OVERWRITE:
                    color = "bright_red"
                elif artifact.map_status == cf.COMPUTE:
                    color = "bright_yellow"

                if artifact.cache_status == cf.IN_CACHE:
                    cache_str = "[bright_green bold](IN CACHE)[/]"
                elif artifact.cache_status == cf.NOT_IN_CACHE:
                    cache_str = "[red](not in cache)[/]"
                elif artifact.cache_status == cf.NO_CACHER:
                    cache_str = "[grey35](no cacher)[/]"

                artifact_str = f"     {artifact.contextualized_name}".ljust(55)
                artifact_str += f"{cf.status(artifact.map_status)}".ljust(10)
                # artifact_str += cache_str

                map_str += f"[{color}]{artifact_str}[/{color}]{cache_str}\n"

                # console.print(f"\t[{color}]{artifact.contextualized_name} ---- {cf.status(artifact.map_status)}[/{color}]\t{cache_str}")
        map_str += "\n"

    artifact_total = (
        artifact_counts["to_compute"]
        + artifact_counts["use_cache"]
        + artifact_counts["skipped"]
    )
    stage_total = stage_counts["to_compute"] + stage_counts["skipped"]
    to_compute = artifact_counts["to_compute"]
    found_in_cache = artifact_counts["found_in_cache"]
    stages_to_compute = stage_counts["to_compute"]
    map_str += f"Artifacts to compute: [bold]{to_compute}[/]/{artifact_total} ({found_in_cache} in cache)\n"
    map_str += f"Stages to compute: [bold]{stages_to_compute}[/]/{stage_total}"

    console.print(map_str)


def cmd_ls(parsed, parser, ls_parser):  # noqa: C901
    manager = cf.get_manager()
    if parsed.debug:
        manager.logger.setLevel(logging.DEBUG)
        manager.init_root_logging()

    if not parsed.list_runs:
        manager.load_default_pipeline_imports()
        if parsed.thing_to_list is not None:
            manager.import_pipelines_from_module(parsed.thing_to_list)
        print_load_failures(parsed.debug)

    search = parsed.thing_to_list
    if search is None:
        search = ""

    if parsed.list_runs:
        resolved = manager.resolve_reference(search, types=["runs"])
        for entry in resolved["reference_names"]:
            print(entry)
        exit()

    if parsed.list_paths:
        resolved = manager.resolve_reference(search)
        for artifact in resolved["artifact_list"]:
            if artifact.cacher is not None:
                print(artifact.cacher.load_paths())
        exit()

    resolved = manager.resolve_reference(search)
    # print(resolved)
    if (
        "artifact_list" in resolved and len(resolved["artifact_list"]) > 0
    ):  # TODO: why is a blank artifact_list sometimes being added?
        print(f"Artifacts matching {search}:")
        for artifact in resolved["artifact_list"]:
            print(
                artifact.name.ljust(20),
                f" (stage: {artifact.compute.name})".ljust(40),
                f"(context: {artifact.context_name})".ljust(40),
            )
    elif "pipeline_instance" in resolved:
        print(f"Artifacts in pipeline {search}:")
        for artifact in resolved["pipeline_instance"].artifacts:
            print(
                artifact.name.ljust(20),
                f" (stage: {artifact.compute.name})".ljust(40),
                f"(context: {artifact.context_name})".ljust(40),
            )
    elif "reference_instance" in resolved and search != "":
        instance_name = resolved["reference_instance"].name
        print(f"Artifacts in reference {instance_name}:")
        for artifact in resolved["reference_instance"].artifacts:
            if artifact.compute is not None:
                print(
                    artifact.name.ljust(20),
                    f" (stage: {artifact.compute.name})".ljust(40),
                    f"(context: {artifact.context_name})".ljust(40),
                )
            else:
                print(
                    artifact.name.ljust(20),
                    "".ljust(40),
                    f"(context: {artifact.context_name})".ljust(40),
                )
    else:
        if search == "":
            print("Pipelines:")
        else:
            print(f"Pipelines matching '{search}':")
        for exp_key, exp_val in resolved["pipeline_instance_list"].items():
            print(f"{exp_key} ({exp_val.name})")

        print("---")
        if search == "":
            print("Pipeline classes:")
        else:
            print(f"Pipeline classes matching '{search}':")
        for exp_class in resolved["pipeline_class_list"]:
            print(exp_class.__name__)


def cmd_reports(parsed, parser, reports_parser):
    import os

    manager = cf.get_manager()
    os.chdir(manager.reports_path)
    cf.utils.run_command(
        ["python", "-m", "http.server", str(parsed.port)]  # , "--bind", args.host]
    )
    os.chdir("..")


def main():  # noqa: C901
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )

    subparsers = parser.add_subparsers(help="Commands:", dest="command")

    conf_parser = subparsers.add_parser(
        "config", help="View/edit curifactory configuration"
    )
    conf_parser.add_argument("--debug", "--verbose", action="store_true", dest="debug")

    db_parser = subparsers.add_parser(
        "db",
        help="Run database commands or open python terminal with duckdb database loaded",
    )
    db_subparsers = db_parser.add_subparsers(help="Commands:", dest="sub_command")
    db_subparsers.add_parser(
        "version",
        help="Print schema version",
    )
    db_subparsers.add_parser(
        "verify",
        help="Check the store table schemas for errors",
    )
    db_subparsers.add_parser(
        "migrate",
        help="Update database from previous version to current",
    )
    db_fix_subparser = db_subparsers.add_parser(
        "fix",
        help="Apply manual fixes",
    )
    for fix in cf.db_tables.FIXES:
        db_fix_subparser.add_argument(f"--{fix}", action="store_true", dest=fix)

    ls_parser = subparsers.add_parser("ls", help="List pipelines")
    ls_parser.add_argument("thing_to_list", nargs="?")
    ls_parser.add_argument(
        "-r",
        "--runs",
        dest="list_runs",
        action="store_true",
        help="List previous pipeline run names in database",
    )
    ls_parser.add_argument(
        "--paths", dest="list_paths", action="store_true", help="List artifact paths"
    )
    ls_parser.add_argument("--debug", "--verbose", action="store_true", dest="debug")

    run_parser = subparsers.add_parser("run", help="Run an pipeline", add_help=False)
    run_parser.add_argument("pipeline").completer = completer_pipeline
    run_parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )
    run_parser.add_argument(
        "--ow",
        "--overwrite",
        action="append",
        dest="overwrite",
        help="Overwrite specific artifacts during run.",
    )
    run_parser.add_argument(
        "--overwrite-all", dest="overwrite_all", action="store_true"
    )
    run_parser.add_argument(
        "-r",
        "--replace",
        action="append",
        dest="replace",
        help="Replace specific artifacts with other artifacts.",
    )
    run_parser.add_argument("--debug", "--verbose", action="store_true", dest="debug")

    map_parser = subparsers.add_parser(
        "map", help="Map out what needs to execute and what doesn't."
    )
    map_parser.add_argument("pipeline")
    map_parser.add_argument(
        "--ow",
        "--overwrite",
        action="append",
        dest="overwrite",
        help="Overwrite specific artifacts during run.",
    )
    map_parser.add_argument(
        "--overwrite-all", dest="overwrite_all", action="store_true"
    )
    map_parser.add_argument(
        "-r",
        "--replace",
        action="append",
        dest="replace",
        help="Replace specific artifacts with other artifacts.",
    )

    # diag_parser = subparsers.add_parser("diagram", help="Render pipeline diagram")
    # diag_parser.add_argument("pipeline")

    reports_parser = subparsers.add_parser("reports", help="Run HTML reports server")
    reports_parser.add_argument("-p", "--port")

    argcomplete.autocomplete(parser, always_complete_options=False)
    argcomplete.autocomplete(run_parser, always_complete_options=False)
    parsed, unknown = parser.parse_known_args()
    # print(parsed)

    # initial help check
    if parsed.show_help:
        if parsed.command is None:
            parser.print_help()
            return
        if parsed.command == "run":
            if parsed.pipeline is None:
                run_parser.print_help()
                return

    if parsed.command == "run":
        cmd_run(parsed, parser, run_parser)
    # elif parsed.command == "diagram":
    #     manager = cf.get_manager()
    #     manager.load_default_pipeline_imports()
    #
    #     search = parsed.pipeline
    #     resolved = manager.resolve_reference(search)
    #
    #     pipeline = None
    #     if "pipeline_instance" in resolved:
    #         pipeline = resolved["pipeline_instance"]
    #
    #     if pipeline is not None:
    #         dot = pipeline.visualize()
    #         # print(dot.pipe(format="kitty"))
    #         import subprocess
    #         subprocess.run(["/usr/bin/kitty", "icat"], input=dot.pipe(format="kitty"))
    elif parsed.command == "config":
        cmd_config(parsed, parser, conf_parser)
    elif parsed.command == "db":
        cmd_db(parsed, parser, db_parser)
    elif parsed.command == "map":
        cmd_map(parsed, parser, map_parser)
    elif parsed.command == "ls":
        cmd_ls(parsed, parser, ls_parser)
    elif parsed.command == "reports":
        cmd_reports(parsed, parser, reports_parser)


if __name__ == "__main__":
    main()
