"""Tests to make sure the command line interface to running experiments isn't broken."""

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory.cli import completer_experiments, completer_params


def test_experiments_completer():
    """The experiments autocomplete function should return the correct set of
    experiment scripts."""
    output = completer_experiments()
    assert output == ["basic", "subexp.example"]


def test_params_completer():
    """The parameter file autocomplete function should return the correct set of
    parameter files."""
    output = completer_params()
    assert output == ["empty", "nonarrayargs", "params1", "params2", "subparams.thing"]


def test_macos_experiment_completer(mocker):  # noqa: F811
    """The BSD verison of grep on macOS puts './' at the beginning of returned paths,
    we should handle this appropriately"""

    mock = mocker.patch("subprocess.run")
    mock.return_value.stdout = b"./basic.py\n./subexp/example.py\n"

    output = completer_experiments()
    assert output == ["basic", "subexp.example"]


def test_macos_params_completer(mocker):  # noqa: F811
    """The BSD verison of grep on macOS puts './' at the beginning of returned paths,
    we should handle this appropriately"""

    mock = mocker.patch("subprocess.run")
    mock.return_value.stdout = b"./empty.py\n./subparams/thing.py\n"

    output = completer_params()
    assert output == ["empty", "empty", "subparams.thing", "subparams.thing"]
