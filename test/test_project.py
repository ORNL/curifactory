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
    assert os.path.exists("params")
    assert os.path.exists("reports")
