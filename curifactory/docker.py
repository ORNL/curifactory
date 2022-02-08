"""Functions for making a docker image for an experiment run."""

from curifactory import utils


def build_docker(experiment_name, cache_folder, version):
    """Runs the docker build command. This should output the progress
    to the console as it runs.

    Note:
        This assumes your dockerfile is at :code:`docker/dockerfile`.

    Args:
        experiment_name (str): The name of the experiment that was run.
        cache_folder (str): The folder to grab cached objects from.
        version (str): A run number/timestamp.
    """
    cmd_array = [
        "docker",
        "build",
        "-f",
        "docker/dockerfile",
        "--tag",
        f"{experiment_name}:{version}",
        "--tag",
        f"{experiment_name}",
        "--build-arg",
        f"run_folder={cache_folder}",
        # "--build-arg", # NOTE: (01/03/2022) this is not used in the cookiecutter's dockerfile anymore
        # "conda_env_name=test",
        ".",
        "--progress",
        "tty",
    ]  # use plain to see all output
    # cmd_array = ["docker", "build", "-f", "docker/dockerfile", "."]
    utils.run_command(*cmd_array)
