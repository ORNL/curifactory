"""Tests to make sure the command line interface to running experiments isn't broken."""
import argparse

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory.cli import completer_experiments, completer_params, main


def test_experiments_completer():
    """The experiments autocomplete function should return the correct set of
    experiment scripts."""
    output = completer_experiments()
    assert output == ["basic", "simple_cache", "subexp.example"]


def test_params_completer():
    """The parameter file autocomplete function should return the correct set of
    parameter files."""
    output = completer_params()
    assert output == [
        "empty",
        "nonarrayargs",
        "params1",
        "params2",
        "simple_cache",
        "subparams.thing",
    ]


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


def test_experiment_ls_output(mocker, capfd):  # noqa: F811
    """``experiment ls`` should return the list of experiment scripts and parameter files."""
    mock = mocker.patch(  # noqa: F841
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(experiment_name="ls", parameters_name=""),
    )
    test = main()  # noqa: F841
    out, err = capfd.readouterr()
    assert (
        out
        == "EXPERIMENTS:\n\tbasic\n\tsimple_cache\n\tsubexp.example\n\nPARAMS:\n\tempty\n\tnonarrayargs\n\tparams1\n\tparams2\n\tsimple_cache\n\tsubparams.thing\n"
    )
