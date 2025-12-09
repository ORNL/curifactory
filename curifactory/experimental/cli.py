# https://stackoverflow.com/questions/37367331/is-it-possible-to-use-argparse-to-capture-an-arbitrary-set-of-optional-arguments
# https://stackoverflow.com/questions/14950964/overriding-default-argparse-h-behaviour
# https://stackoverflow.com/questions/4042452/display-help-message-with-python-argparse-when-script-is-called-without-any-argu

import argparse
import importlib
import json
import os
import sys
from dataclasses import fields

import argcomplete

import curifactory.experimental as cf


def completer_experiment(**kwargs) -> list[str]:
    manager = cf.get_manager()
    prefix = kwargs["prefix"]
    manager.import_experiments_from_module(prefix)
    return manager.experiment_keys_matching(prefix)


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

    ls_parser = subparsers.add_parser("ls", help="List experiments")
    ls_parser.add_argument("thing_to_list", nargs="?")

    run_parser = subparsers.add_parser("run", help="Run an experiment", add_help=False)
    run_parser.add_argument("experiment").completer = completer_experiment
    run_parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )

    argcomplete.autocomplete(parser, always_complete_options=False)
    argcomplete.autocomplete(run_parser, always_complete_options=False)
    parsed, unknown = parser.parse_known_args()

    # initial help check
    if parsed.show_help:
        if parsed.command is None:
            parser.print_help()
            return
        if parsed.command == "run":
            if parsed.experiment is None:
                run_parser.print_help()
                return

    if parsed.command == "run":
        experiment = None

        manager = cf.get_manager()
        remainder = manager.import_experiments_from_module(parsed.experiment)

        search_parts = manager.divide_reference_parts(parsed.experiment)
        print(search_parts)

        if search_parts["experiment"] in manager.experiment_ref_names:
            experiment = manager.experiment_ref_names[search_parts["experiment"]]

        if experiment is not None:
            experiment_parameter_group = run_parser.add_argument_group(
                f"{experiment.name} parameters", experiment.__doc__
            )

            # add arguments for the experiment to the parser
            names = []
            for field in fields(experiment):
                if field.name in ["name", "outputs"]:
                    continue
                names.append(field.name)
                experiment_parameter_group.add_argument(
                    f"--{field.name}",
                    type=field.type,
                    dest=field.name,
                    help=f"Default: {getattr(experiment, field.name)}",
                )

            parsed_better, _ = parser.parse_known_args()

            new_args = {}
            for name in names:
                if vars(parsed_better)[name] is not None:
                    new_args[name] = vars(parsed_better)[name]

            if len(new_args) > 0:
                experiment = experiment.modify(**new_args)
            # print(experiment)

        if parsed.show_help:
            run_parser.print_help()
            if experiment is None:
                print(f"\nExperiment references matching '{parsed.experiment}':")
                for exp in manager.experiment_keys_matching(parsed.experiment):
                    print("\t", exp, f" ({manager.experiment_ref_names[exp].name})")
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

        if experiment is not None:
            print(experiment)
            manager.init_root_logging()

            if search_parts["artifact_filter"] is None:
                experiment.run()
            else:
                for artifact in experiment.artifacts.filter(
                    search_parts["artifact_filter"]
                ):
                    artifact.get()
                    print(artifact.cacher.load_paths())

    elif parsed.command == "ls":
        manager = cf.get_manager()
        if parsed.thing_to_list is None:
            experiment_list = list(manager.experiment_ref_names.keys())
        else:
            experiment_list = manager.experiment_keys_matching(parsed.thing_to_list)

        if len(experiment_list) == 0:
            search_parts = manager.divide_reference_parts(parsed.thing_to_list)
            experiment = manager.experiment_ref_names[search_parts["experiment"]]
            artifacts = experiment.artifacts.filter(search_parts["artifact_filter"])
            print(f"Artifacts matching {parsed.thing_to_list}:")
            for artifact in artifacts:
                print(
                    artifact.name.ljust(20),
                    f" (stage: {artifact.compute.name})".ljust(40),
                    f"(context: {artifact.context.name})".ljust(40),
                )
        elif parsed.thing_to_list in manager.experiment_ref_names:
            # an exact experiment was listed, list artifacts
            print(f"Artifacts in {parsed.thing_to_list}:")
            for artifact in manager.experiment_ref_names[
                parsed.thing_to_list
            ].artifacts:
                print(
                    artifact.name.ljust(20),
                    f" (stage: {artifact.compute.name})".ljust(40),
                    f"(context: {artifact.context.name})".ljust(40),
                )
        else:
            # otherwise list all matching experiments
            if parsed.thing_to_list is None:
                print("Experiments:")
            else:
                print(f"Experiments matching '{parsed.thing_to_list}':")
            for exp in experiment_list:
                print(exp, f" ({manager.experiment_ref_names[exp].name})")


if __name__ == "__main__":
    main()
