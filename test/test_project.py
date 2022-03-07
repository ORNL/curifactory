"""Testing the `curifactory init` command."""

import os
import pytest
from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory.project import initialize_project


@pytest.mark.noautofixt
def test_project_init_defaults(
    mocker, project_folder  # noqa: F811 -- mocker has to be passed in as fixture
):
    """The default folders should be created when no additional input given."""

    def actual_readline():
        return "\n"

    mocker.patch("sys.stdin.readline", actual_readline)
    initialize_project()

    assert os.path.exists("data")
    assert os.path.exists("docker")
    assert os.path.exists("experiments")
    assert os.path.exists("logs")
    assert os.path.exists("notebooks")
    assert os.path.exists("notebooks/experiments")
    assert os.path.exists("params")
    assert os.path.exists("reports")
    assert os.path.exists("reports/style.css")
    assert os.path.exists(".gitignore")
    assert os.path.exists("curifactory_config.json")


@pytest.mark.noautofixt
def test_project_init_input_nondefaults(
    mocker, project_folder  # noqa: F811 -- mocker has to be passed in as fixture
):
    """Passing a different value to one of the inputs should change the directory and config."""

    prompt_number = 0

    def actual_readline():
        nonlocal prompt_number
        prompt_number += 1
        if prompt_number == 1:
            return "myexperiments\n"
        elif prompt_number == 2:
            return "myparams\n"
        elif prompt_number == 3:
            return "mydata\n"
        elif prompt_number == 4:
            return "mylogs\n"
        elif prompt_number == 5:
            return "mynotebooks\n"
        elif prompt_number == 6:
            return "myreports\n"
        elif prompt_number == 7:  # docker check
            return "n\n"
        elif prompt_number == 8:  # gitignore check
            return "n\n"
        else:
            return "\n"

    mocker.patch("sys.stdin.readline", actual_readline)
    initialize_project()

    assert not os.path.exists("experiments")
    assert os.path.exists("myexperiments")
    assert not os.path.exists("data")
    assert os.path.exists("mydata")
    assert not os.path.exists("docker")
    assert not os.path.exists("logs")
    assert os.path.exists("mylogs")
    assert not os.path.exists("notebooks")
    assert os.path.exists("mynotebooks")
    assert os.path.exists("mynotebooks/experiments")
    assert not os.path.exists("params")
    assert os.path.exists("myparams")
    assert not os.path.exists("reports")
    assert os.path.exists("myreports")
    assert not os.path.exists(".gitignore")
    assert os.path.exists("curifactory_config.json")
