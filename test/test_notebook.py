import os

import curifactory as cf
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
    assert thelocals["state_0"]["my_output"] == 11
    assert thelocals["state_1"]["my_output"] == 15


def test_notebook_uses_correct_cache_path(configured_test_manager):
    """A notebook for a run that used a non-default cache path (e.g. reproducing
    from full store) should set the new manager to use that non-default cache path."""
    results, mngr = run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        build_notebook=True,
        cache_dir_override="test/examples/data/extraspecial_cache",
    )

    assert os.path.exists(mngr.artifacts[-1].file)
    assert "extraspecial_cache" in mngr.artifacts[-1].file

    write_experiment_notebook(
        mngr, "test/examples/notebooks/experiment", leave_script=True
    )

    with open("test/examples/notebooks/experiment.py") as infile:
        code = infile.read()

    code = code.replace("%cd ../..", "")
    thelocals = {}
    exec(code, None, thelocals)
    assert mngr.cache_path == "test/examples/data/extraspecial_cache"
    assert thelocals["manager"].cache_path == "test/examples/data/extraspecial_cache"


def test_dag_mode_doesnot_interfere_after_experiment_in_notebook(
    configured_test_manager,
):
    """After an experiment has been run from inside a notebook, DAG mode should be disabled
    so that additional stages can be run inside."""

    @cf.stage(["my_output"], ["modified_output"])
    def modify_output(record, my_output):
        return my_output + 3

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

    modify_output(thelocals["record_0"])

    assert thelocals["record_0"].state["modified_output"] == 14
