# https://stackoverflow.com/questions/37367331/is-it-possible-to-use-argparse-to-capture-an-arbitrary-set-of-optional-arguments
# https://stackoverflow.com/questions/14950964/overriding-default-argparse-h-behaviour
# https://stackoverflow.com/questions/4042452/display-help-message-with-python-argparse-when-script-is-called-without-any-argu

import argparse
import importlib
import json
import logging
import os
import sys
from dataclasses import MISSING, fields

import argcomplete
from rich.console import Console

import curifactory.experimental as cf


def completer_pipeline(**kwargs) -> list[str]:
    # manager = cf.get_manager()
    # prefix = kwargs["prefix"]
    # manager.import_pipelines_from_module(prefix)
    # return manager.pipeline_keys_matching(prefix)
    return []


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )

    subparsers = parser.add_subparsers(help="Commands:", dest="command")

    ls_parser = subparsers.add_parser("ls", help="List pipelines")
    ls_parser.add_argument("thing_to_list", nargs="?")
    ls_parser.add_argument("-r", "--runs", dest="list_runs", action="store_true", help="List previous pipeline run names in database")

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
    run_parser.add_argument("--overwrite-all")
    run_parser.add_argument("--debug", action="store_true", dest="debug")

    map_parser = subparsers.add_parser("map", help="Map out what needs to execute and what doesn't.")
    map_parser.add_argument("pipeline")

    diag_parser = subparsers.add_parser("diagram", help="Render pipeline diagram")
    diag_parser.add_argument("pipeline")

    argcomplete.autocomplete(parser, always_complete_options=False)
    argcomplete.autocomplete(run_parser, always_complete_options=False)
    parsed, unknown = parser.parse_known_args()
    print(parsed)

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
        pipeline = None

        manager = cf.get_manager()
        manager.load_default_pipeline_imports()
        remainder = manager.import_pipelines_from_module(parsed.pipeline)

        search = parsed.pipeline
        resolved = manager.resolve_reference(search)

        if "pipeline_instance" in resolved:
            pipeline = resolved["pipeline_instance"]
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
                print("I was called with", string)
                resolved = manager.resolve_reference(string)
                print(resolved)
                if "pipeline_instance" in resolved:
                    print("FOUND!")
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
                print(field.name, field.type, field.type.__name__)
                if field.type.__name__ == "list":
                    # https://stackoverflow.com/questions/47077329/python-get-type-of-typing-list
                    print("LIST!")
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
                    print(new_args)
                    pipeline = pipeline(pipeline.__name__, **new_args)
                else:
                    pipeline = pipeline.modify(**new_args)

            # print(pipeline)

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

                # print(f"\nExperiment references matching '{parsed.experiment}':")
                # for exp in manager.experiment_keys_matching(parsed.experiment):
                #     print("\t", exp, f" ({manager.experiment_ref_names[exp].name})")
                # for key in manager.experiment_ref_names.keys():
                #     print(key)
                # print(f"\nExperiments in {module.__name__}:")
                # for exp in cf.get_manager().experiments:
                #     print(f"\t{exp.__name__}")
                #     for parameterized in cf.get_manager().parameterized_experiments[
                #         exp
                #     ]:
                #         if parameterized in found_experiments.values():
                #             print(
                #                 f"\t\t{list(found_experiments.keys())[list(found_experiments.values()).index(parameterized)]} ({parameterized.name})"
                #             )
            return

        if pipeline is not None:
            print(pipeline)
            manager.init_root_logging()
            if parsed.debug:
                print("Yep it's debug")
                # logging.getLogger("curifactory").setLevel(logging.DEBUG)
                manager.logger.setLevel(logging.DEBUG)
                # logging.getLogger().setLevel(logging.DEBUG)

            # handle overwrites
            if parsed.overwrite is not None:
                for overwrite_req in parsed.overwrite:
                    art_resolved = manager.resolve_reference(overwrite_req)
                    if "artifact" not in art_resolved and "artifact_list" not in art_resolved:
                        print(f"COULD NOT FIND {overwrite_req}.")
                        exit()
                    else:
                        if "artifact" in art_resolved:
                            art_resolved["artifact"].overwrite = True
                            manager.logger.debug(f"Setting overwrite on art_{art_resolved['artifact'].name}")
                        else:
                            for artifact in art_resolved["artifact_list"]:
                                manager.logger.debug(f"Setting overwrite on art_{artifact.name}")
                                artifact.ovewrite = True

            if "artifact" not in resolved and "artifact_list" not in resolved:
                print(pipeline)
                pipeline.run()
            # if search_parts["artifact_filter"] is None:
            else:
                if "artifact" in resolved:
                    manager.logger.debug(f"Attempting to get Artifact '{resolved["artifact"].name}'")
                    resolved["artifact"].get()
                elif "artifact_list" in resolved:
                    manager.logger.debug(f"Attempting to get Artifacts {[artifact.name for artifact in resolved['artifact_list']]}")
                    for artifact in resolved["artifact_list"]:
                        artifact.get()
                # for artifact in pipeline.artifacts.filter(
                #     search_parts["artifact_filter"]
                # ):
                #     artifact.get()
                #     print(artifact.cacher.load_paths())

    elif parsed.command == "diagram":
        manager = cf.get_manager()
        manager.load_default_pipeline_imports()

        search = parsed.pipeline
        resolved = manager.resolve_reference(search)

        pipeline = None
        if "pipeline_instance" in resolved:
            pipeline = resolved["pipeline_instance"]

        if pipeline is not None:
            dot = pipeline.visualize()
            # print(dot.pipe(format="kitty"))
            import subprocess
            subprocess.run(["/usr/bin/kitty", "icat"], input=dot.pipe(format="kitty"))

    elif parsed.command == "map":
        manager = cf.get_manager()
        manager.load_default_pipeline_imports()

        search = parsed.pipeline
        resolved = manager.resolve_reference(search)

        pipeline = None
        if "pipeline_instance" in resolved:
            pipeline = resolved["pipeline_instance"]

        if pipeline is not None:
            if "artifact" not in resolved and "artifact_list" not in resolved:
                mapped = pipeline.map()
            elif "artifact" in resolved:
                mapped = resolved["artifact"].map()
            elif "artifact_list" in resolved:
                mapped = None
                for artifact in resolved["artifact_list"]:
                    mapped = artifact.map(mapped)

        artifact_counts = {"to_compute": 0, "use_cache": 0, "skipped": 0, "found_in_cache": 0}
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

        console = Console()
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

        artifact_total = artifact_counts["to_compute"] + artifact_counts["use_cache"] + artifact_counts["skipped"]
        stage_total = stage_counts["to_compute"] + stage_counts["skipped"]
        map_str += f"Artifacts to compute: [bold]{artifact_counts["to_compute"]}[/]/{artifact_total} ({artifact_counts["found_in_cache"]} in cache)\n"
        map_str += f"Stages to compute: [bold]{stage_counts["to_compute"]}[/]/{stage_total}"

        console.print(map_str)

    elif parsed.oommand == "ls":
        manager = cf.get_manager()

        if not parsed.list_runs:
            manager.load_default_pipeline_imports()

        search = parsed.thing_to_list
        if search is None:
            search = ""

        if parsed.list_runs:
            resolved = manager.resolve_reference(search, types=["runs"])
            for entry in resolved["reference_names"]:
                print(entry)
            exit()

        resolved = manager.resolve_reference(search)
        if "artifact_list" in resolved:
            print(f"Artifacts matching {search}:")
            for artifact in resolved["artifact_list"]:
                print(
                    artifact.name.ljust(20),
                    f" (stage: {artifact.compute.name})".ljust(40),
                    f"(context: {artifact.context_name})".ljust(40),
                )
        elif "pipeline_instance" in resolved:
            print(f"Artifacts in {search}:")
            for artifact in resolved["pipeline_instance"].artifacts:
                print(
                    artifact.name.ljust(20),
                    f" (stage: {artifact.compute.name})".ljust(40),
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


        # if parsed.thing_to_list is None:
        #     experiment_list = list(manager.experiment_ref_names.keys())
        # else:
        #     experiment_list = manager.experiment_keys_matching(parsed.thing_to_list)
        #
        # if len(experiment_list) == 0:
        #     search_parts = manager.divide_reference_parts(parsed.thing_to_list)
        #     experiment = manager.experiment_ref_names[search_parts["experiment"]]
        #     artifacts = experiment.artifacts.filter(search_parts["artifact_filter"])
        #     print(f"Artifacts matching {parsed.thing_to_list}:")
        #     for artifact in artifacts:
        #         print(
        #             artifact.name.ljust(20),
        #             f" (stage: {artifact.compute.name})".ljust(40),
        #             f"(context: {artifact.context.name})".ljust(40),
        #         )
        # elif parsed.thing_to_list in manager.experiment_ref_names:
        #     # an exact experiment was listed, list artifacts
        #     print(f"Artifacts in {parsed.thing_to_list}:")
        #     for artifact in manager.experiment_ref_names[
        #         parsed.thing_to_list
        #     ].artifacts:
        #         print(
        #             artifact.name.ljust(20),
        #             f" (stage: {artifact.compute.name})".ljust(40),
        #             f"(context: {artifact.context.name})".ljust(40),
        #         )
        # else:
        #     # otherwise list all matching experiments
        #     if parsed.thing_to_list is None:
        #         print("Experiments:")
        #     else:
        #         print(f"Experiments matching '{parsed.thing_to_list}':")
        #     for exp in experiment_list:
        #         print(exp, f" ({manager.experiment_ref_names[exp].name})")
        #
        #     print("---")
        #     for exp_class in manager.experiments:
        #         print(exp_class.__name__)


if __name__ == "__main__":
    main()
