import curifactory.utils
from curifactory import docker

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture


def test_build_docker(mocker):  # noqa: F811 -- mocker has to be passed in as fixture
    """This is mostly just to make sure the docker command isn't changed from what we
    expect without a notification."""

    mocker.patch("curifactory.utils.run_command")
    docker.build_docker("test_name", "./test_cache_folder", "some_version_string")

    curifactory.utils.run_command.assert_called_once_with(
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
    )
