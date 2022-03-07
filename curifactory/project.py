"""This is the 'meta' curifactory CLI, which is a runnable to help set up a
project structure.

This file contains a :code:`__name__ == "__main__"` and can be run directly.
"""

import argparse
import json
import os
import pkg_resources
import shutil

import curifactory as cf
from curifactory import utils


def initialize_project():
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
    style_path = pkg_resources.resource_filename("curifactory", "data/style.css")
    shutil.copyfile(style_path, config["report_css_path"])

    # handle docker folder and dockerfile
    valid_docker_choice = False
    while not valid_docker_choice:
        docker_yn = input("Include docker folder and default dockerfile? [Y/n] ")
        if docker_yn == "" or docker_yn.lower() == "y":
            valid_docker_choice = True
            print("Setting up docker folder...")
            os.makedirs("docker", exist_ok=True)

            # read in the dockerfile contents and edit appropriately
            dockerfile_path = pkg_resources.resource_filename(
                "curifactory", "data/dockerfile"
            )
            with open(dockerfile_path, "r") as infile:
                contents = infile.read()
                contents.replace("{{CF_VERSION}}", cf.__version__)
            with open("docker/dockerfile", "w") as outfile:
                outfile.write(contents)

            dockerfile_start_path = pkg_resources.resource_filename(
                "curifactory", "data/startup.sh"
            )
            shutil.copyfile(dockerfile_start_path, "docker/startup.sh")

            dockerfile_ignore_path = pkg_resources.resource_filename(
                "curifactory", "data/.dockerignore"
            )
            shutil.copyfile(dockerfile_ignore_path, "docker/.dockerignore")
        elif docker_yn.lower() == "n":
            valid_docker_choice = True
        if not valid_docker_choice:
            print("Invalid entry, please enter 'y' or 'n', or leave blank for default.")

    # handle gitignore
    valid_gitfile_choice = False
    while not valid_gitfile_choice:
        gitfile_yn = input("Append curifactory paths to .gitignore? [Y/n] ")
        if gitfile_yn == "" or gitfile_yn.lower() == "y":
            valid_gitfile_choice = True

            newline_needed = False
            if os.path.exists(".gitignore"):
                with open(".gitignore", "r") as infile:
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


def main():

    # TODO: could add the reset functionality as requested in this runnable.

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subparser_name")
    init_parser = subparsers.add_parser("init")  # noqa: F841 -- we might use eventually

    args = parser.parse_args()
    if args.subparser_name == "init":
        initialize_project()


if __name__ == "__main__":
    main()
