import os

from curifactory.experiment import run_experiment
from curifactory.notebook import write_experiment_notebook


def test_experiment_cli_creates_notebook(configured_test_manager):
    """Running an experiment with `--notebook` should create a notebook file."""

    results, mngr = run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        build_notebook=True,
    )

    assert os.path.exists(
        f"test/examples/notebooks/experiments/{mngr.get_reference_name()}.ipynb"
    )


def test_experiment_notebook_is_runnable(configured_test_manager):
    """The notebook generated for an experiment should be runnable."""

    results, mngr = run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        build_notebook=True,
    )

    write_experiment_notebook(
        mngr, "test/examples/notebooks/experiment", leave_script=True
    )

    with open("test/examples/notebooks/experiment.py") as infile:
        code = infile.read()

    code = code.replace("%cd ../..", "")
    thelocals = {}
    exec(code, None, thelocals)
    assert thelocals["state0"]["my_output"] == 11
    assert thelocals["state1"]["my_output"] == 15


# TODO: test that cache_path is provided to manager

# TODO: test can run new stages after experiment run in notebook
