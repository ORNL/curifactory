from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

import curifactory.utils
from curifactory import docker
from curifactory.experiment import run_experiment


def test_build_docker(mocker):  # noqa: F811 -- mocker has to be passed in as fixture
    """This is mostly just to make sure the docker command isn't changed from what we
    expect without a notification."""

    mocker.patch("curifactory.utils.run_command")
    docker.build_docker("test_name", "./test_cache_folder", "some_version_string")

    curifactory.utils.run_command.assert_called_once_with(
        [
            "docker",
            "build",
            "-f",
            "docker/dockerfile",
            "--tag",
            "test_name:some_version_string",
            "--tag",
            "test_name",
            "--build-arg",
            "run_folder=./test_cache_folder",
            ".",
            "--progress",
            "tty",
        ]
    )


def test_build_docker_gets_correct_run_folder(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    configured_test_manager,
):
    """The name of the run folder passed to build_docker should be correct and not have the last
    letter cut off."""
    # mocker.patch("curifactory.utils.run_command")
    mocker.patch("curifactory.utils.run_command")

    results, manager = run_experiment(
        "basic", ["params1"], mngr=configured_test_manager, build_docker=True
    )
    run_num = manager.experiment_run_number
    datestr = manager.run_timestamp.strftime("%Y-%m-%d")
    curifactory.utils.run_command.assert_called_once_with(
        [
            "docker",
            "build",
            "-f",
            "docker/dockerfile",
            "--tag",
            f"basic:{run_num}_{datestr}",
            "--tag",
            "basic",
            "--build-arg",
            f"run_folder=test/examples/data/runs/test_{run_num}_{manager.run_timestamp.strftime(curifactory.utils.TIMESTAMP_FORMAT)}",
            ".",
            "--progress",
            "tty",
        ]
    )
