"""This is the 'meta' curifactory CLI, which is a runnable to help set up a
project structure.

This file contains a :code:`__name__ == "__main__"` and can be run directly.
"""

import argparse
import importlib.resources
import json
import os
import shutil

import curifactory as cf
from curifactory import utils


def initialize_project():  # noqa: C901 yeaaaah break up into sub functions
    print("Initializing curifactory project...")
    print(
        "Enter paths for configuration file, default values shown in '[]' (leave entry blank to use default)"
    )
    if os.path.exists(utils.CONFIGURATION_FILE):
        print(
            "NOTE: existing curifactory configuration found, default values are now currently existing values."
        )
    config = utils.get_configuration()

    def query_value_and_update(config, query, key):
        value = input(f"{query} ['{config[key]}']: ")
        if value != "":
            config[key] = value

    query_value_and_update(config, "Experiments module name", "experiments_module_name")
    query_value_and_update(config, "Parameters module name", "params_module_name")
    query_value_and_update(config, "Data path", "manager_cache_path")
    config["cache_path"] = os.path.join(config["manager_cache_path"], "cache/")
    config["runs_path"] = os.path.join(config["manager_cache_path"], "runs/")
    query_value_and_update(config, "Logs path", "logs_path")
    query_value_and_update(config, "Notebooks path", "notebooks_path")
    query_value_and_update(config, "Reports path", "reports_path")
    config["report_css_path"] = os.path.join(config["reports_path"], "style.css")

    # write out config
    print("Writing config file...")
    with open("curifactory_config.json", "w") as outfile:
        json.dump(config, outfile, indent=4)

    # create directory structure
    print("Setting up folders...")
    os.makedirs(config["experiments_module_name"], exist_ok=True)
    os.makedirs(config["params_module_name"], exist_ok=True)
    os.makedirs(config["manager_cache_path"], exist_ok=True)
    os.makedirs(config["cache_path"], exist_ok=True)
    os.makedirs(config["runs_path"], exist_ok=True)
    os.makedirs(config["logs_path"], exist_ok=True)
    os.makedirs(config["notebooks_path"], exist_ok=True)
    os.makedirs(os.path.join(config["notebooks_path"], "experiments"), exist_ok=True)
    os.makedirs(config["reports_path"], exist_ok=True)

    # copy in style sheet for reports
    # style_path = pkg_resources.resource_filename("curifactory", "data/style.css")
    with importlib.resources.as_file(
        importlib.resources.files("curifactory") / "data/style.css"
    ) as style_path:
        shutil.copyfile(style_path, config["report_css_path"])

    # copy in debug.py for easier IDE debugging entrypoint
    with importlib.resources.as_file(
        importlib.resources.files("curifactory") / "data/debug.py"
    ) as debug_file_path:
        shutil.copyfile(debug_file_path, "debug.py")

    # handle docker folder and dockerfile
    valid_docker_choice = False
    while not valid_docker_choice:
        docker_yn = input("Include docker folder and default dockerfile? [Y/n] ")
        if docker_yn == "" or docker_yn.lower() == "y":
            valid_docker_choice = True
            print("Setting up docker folder...")
            os.makedirs("docker", exist_ok=True)

            # read in the dockerfile contents and edit appropriately
            with importlib.resources.as_file(
                importlib.resources.files("curifactory") / "data/dockerfile"
            ) as dockerfile_path:
                with open(dockerfile_path) as infile:
                    contents = infile.read()
                    contents.replace("{{CF_VERSION}}", cf.__version__)
                with open("docker/dockerfile", "w") as outfile:
                    outfile.write(contents)

            with importlib.resources.as_file(
                importlib.resources.files("curifactory") / "data/startup.sh"
            ) as dockerfile_start_path:
                shutil.copyfile(dockerfile_start_path, "docker/startup.sh")

            with importlib.resources.as_file(
                importlib.resources.files("curifactory") / "data/.dockerignore"
            ) as dockerfile_ignore_path:
                shutil.copyfile(dockerfile_ignore_path, "docker/.dockerignore")
        elif docker_yn.lower() == "n":
            valid_docker_choice = True
        if not valid_docker_choice:
            print("Invalid entry, please enter 'y' or 'n', or leave blank for default.")

    # if this isn't being run in a git repository, ask the user if they want to git init
    if not os.path.exists(".git"):
        print(
            "No .git folder found. Curifactoy expects to run from within a git repository."
        )
        valid_gitinit_choice = False
        while not valid_gitinit_choice:
            gitinit_yn = input("Run `git init`? [y/N]")
            if gitinit_yn.lower() == "y":
                valid_gitinit_choice = True
                utils.run_command(["git", "init"])
            elif gitinit_yn == "" or gitinit_yn.lower() == "n":
                valid_gitinit_choice = True
            if not valid_gitinit_choice:
                print(
                    "Invalid entry, please enter 'y' or 'n', or leave blank for default."
                )

    # handle gitignore
    valid_gitfile_choice = False
    while not valid_gitfile_choice:
        gitfile_yn = input("Append curifactory paths to .gitignore? [Y/n] ")
        if gitfile_yn == "" or gitfile_yn.lower() == "y":
            valid_gitfile_choice = True

            newline_needed = False
            if os.path.exists(".gitignore"):
                with open(".gitignore") as infile:
                    lines = infile.readlines()
                    if len(lines) > 0 and lines[-1] != "\n":
                        newline_needed = True

            print("Appending to .gitignore...")
            with open(".gitignore", "a") as outfile:
                if newline_needed:
                    outfile.write("\n")
                outfile.write(
                    "\n".join(
                        [
                            "# curifactory paths",
                            os.path.join(config["manager_cache_path"], "*"),
                            os.path.join(config["cache_path"], "*"),
                            os.path.join(config["runs_path"], "*"),
                            os.path.join(config["logs_path"], "*"),
                            os.path.join(config["reports_path"], "*"),
                            "!" + config["report_css_path"],
                        ]
                    )
                )
        elif gitfile_yn.lower() == "n":
            valid_gitfile_choice = True
        if not valid_gitfile_choice:
            print("Invalid entry, please enter 'y' or 'n', or leave blank for default.")

    print("Curifactory project initialization complete!")
    add_completion_to_rc(False, False)


def add_completion_to_rc(bash=False, zsh=False):
    print(
        "\nFor bash/zsh completion to work, the argcomplete package needs to be installed (outside a conda environment)"
    )
    print("You can use `pip install argcomplete`")

    print("\nEnabling completion can then be done in three different ways:")
    print(
        "* Globally for all argcomplete python packages: \n\tsudo activate-global-python-argcomplete"
    )
    print(
        '* Single shell instance: \n\teval "$(register-python-argcomplete experiment)"'
    )
    print(
        "* Permanent non-globally for curifactory (RECOMMENDED):\n\tcurifactory completion --bash --zsh\n\tOr simply add single shell instance manually to any sourced shell rc file."
    )

    shell_string = '# tab-completion hook for curifactory\neval "$(register-python-argcomplete experiment)"'
    print(f"\n{shell_string}\n")

    if bash:
        print("Writing tab-completion hook into '~/.bashrc'...")
        with open(os.path.expanduser("~/.bashrc"), "a") as bashrc:
            bashrc.write(f"\n{shell_string}\n")
    if zsh:
        print("Writing tab-completion hook into '~/.zshrc'...")
        with open(os.path.expanduser("~/.zshrc"), "a") as zshrc:
            zshrc.write(f"\n{shell_string}\n")


def main():
    # TODO: could add the reset functionality as requested in this runnable.

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--version",
        dest="version",
        action="store_true",
        help="Print the current version of the curifactory library.",
    )

    subparsers = parser.add_subparsers(dest="subparser_name")

    init_parser = subparsers.add_parser("init")  # noqa: F841 -- we might use eventually

    completion_parser = subparsers.add_parser("completion")
    completion_parser.add_argument("--bash", dest="bash", action="store_true")
    completion_parser.add_argument("--zsh", dest="zsh", action="store_true")

    args = parser.parse_args()

    if args.version:
        print(cf.__version__)
        quit()

    if args.subparser_name == "init":
        initialize_project()
    elif args.subparser_name == "completion":
        add_completion_to_rc(args.bash, args.zsh)


if __name__ == "__main__":
    main()
