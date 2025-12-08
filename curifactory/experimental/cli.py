# https://stackoverflow.com/questions/37367331/is-it-possible-to-use-argparse-to-capture-an-arbitrary-set-of-optional-arguments
# https://stackoverflow.com/questions/14950964/overriding-default-argparse-h-behaviour
# https://stackoverflow.com/questions/4042452/display-help-message-with-python-argparse-when-script-is-called-without-any-argu

import argparse
import importlib
import os
import sys
from dataclasses import fields

import curifactory.experimental as cf


def main():
    sys.path.append(os.getcwd())
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )

    subparsers = parser.add_subparsers(help="Subcommand help", dest="command")

    run_parser = subparsers.add_parser("run", help="Run help", add_help=False)
    run_parser.add_argument("experiment")
    run_parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        dest="show_help",
        help="Show this help message",
    )

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
        # see if only a module was provided
        found_experiments = {}
        try:
            module = importlib.import_module(parsed.experiment)
            experiment = None
        except ModuleNotFoundError:
            module = importlib.import_module(
                ".".join(parsed.experiment.split(".")[:-1])
            )
            try:
                experiment = getattr(module, parsed.experiment.split(".")[-1])
            except AttributeError:
                experiment = None

        for attr in dir(module):
            if isinstance(getattr(module, attr), cf.experiment.Experiment):
                found_experiments[attr] = getattr(module, attr)

                # print(f"Found: {attr}")
                # print(f"Looking for {module}")
                # for exp, param_list in cf.get_manager().parameterized_experiments.items():
                #     pass
        # print(module)
        # print(experiment)

        # if experiment is None:
        #     print(cf.get_manager().experiments)
        #     print(cf.get_manager().parameterized_experiments)

        if experiment is not None:
            # print(type(experiment))
            if type(experiment).__name__ == "ExperimentFactoryWrapper":
                experiment = experiment(f"{experiment.type_name}_default")
            # experiment.run()

            # print(experiment.parameters)
            # print(fields(experiment))
            experiment_parameter_group = run_parser.add_argument_group(
                f"{experiment.name} parameters", experiment.__doc__
            )

            names = []
            for field in fields(experiment):
                if field.name in ["name", "outputs"]:
                    continue
                names.append(field.name)
                # print(field.name, field.type, field.default_factory())
                # experiment_parameter_group.add_argument(f"--{field.name}", type=field.type, dest=field.name, help=f"Default: {field.default_factory()}")
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
                print(f"\nExperiments in {module.__name__}:")
                for exp in cf.get_manager().experiments:
                    print(f"\t{exp.__name__}")
                    for parameterized in cf.get_manager().parameterized_experiments[
                        exp
                    ]:
                        if parameterized in found_experiments.values():
                            print(
                                f"\t\t{list(found_experiments.keys())[list(found_experiments.values()).index(parameterized)]} ({parameterized.name})"
                            )
            return

        if experiment is not None:
            experiment.run()
            print(experiment.compute_hash())

            # run_parser.print_help()

        # experiment_module = ".".join(parsed.experiment.split(".")[:-1])
        # if experiment_module == "":
        #     experiment_module = parsed.experiment
        # print(parsed.experiment)
        # print(os.getcwd())
        # module = importlib.import_module(experiment_module)
        # print(module)
        # next_thing = parsed.experiment.split(".")[-1]
        # print(getattr(module, next_thing))


if __name__ == "__main__":
    main()
