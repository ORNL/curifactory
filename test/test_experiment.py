"""These are integration and unit tests for the overall experiment calls."""

import os
import pytest
from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory.experiment import run_experiment
from curifactory.manager import ArtifactManager


# TODO: need to test that specifying no params will default to experiment_name


@pytest.mark.parametrize(
    "experiment_params,expected_manager_params",
    [
        (
            dict(experiment_name="test", parameters_list=["params1", "params2"]),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test -p params1 -p params2",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(experiment_name="test", parameters_list=[]),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(
                experiment_name="test",
                parameters_list=["params1"],
                cache_dir_override="test/examples/data/superspecialcache",
            ),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test -p params1 --cache test/examples/data/superspecialcache",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(
                experiment_name="test",
                parameters_list=["params1"],
                store_entire_run=True,
            ),
            dict(
                store_entire_run=True,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test -p params1 --store-full",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(
                experiment_name="test",
                parameters_list=["params1"],
                dry=True,
                dry_cache=True,
            ),
            dict(
                store_entire_run=False,
                dry=True,
                dry_cache=True,
                custom_name=None,
                run_line="experiment test -p params1 --dry --dry-cache",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(
                experiment_name="test",
                parameters_list=["params1"],
                custom_name="custom_test",
            ),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name="custom_test",
                run_line="experiment test -p params1 --name custom_test",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=False,
            ),
        ),
        (
            dict(experiment_name="test", parameters_list=["params1"], lazy=True),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test -p params1 --lazy",
                parallel_lock=None,
                parallel_mode=False,
                lazy=True,
                ignore_lazy=False,
            ),
        ),
        (
            dict(experiment_name="test", parameters_list=["params1"], ignore_lazy=True),
            dict(
                store_entire_run=False,
                dry=False,
                dry_cache=False,
                custom_name=None,
                run_line="experiment test -p params1 --ignore-lazy",
                parallel_lock=None,
                parallel_mode=False,
                lazy=False,
                ignore_lazy=True,
            ),
        ),
    ],
)
def test_manager_integration(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    experiment_params,
    expected_manager_params,
):
    """Manager initialization calls should have the correct parameters passed to it based on the run_experiment call."""
    mock = mocker.patch.object(ArtifactManager, "__init__", return_value=None)

    try:
        run_experiment(**experiment_params)
    except AttributeError:
        # NOTE: I'm not actually sure a better way around this, all I want to test is that
        # manager was initialized with what I expect
        pass
    mock.assert_called_once_with(
        "test", **expected_manager_params, status_override=None, notes=None
    )


@pytest.mark.parametrize(
    "local_rank,node_rank,expect_parallel",
    [
        (None, None, False),
        (0, None, False),
        (1, None, True),
        (0, 0, False),
        (1, 0, True),
        (0, 1, True),
        (1, 1, True),
    ],
)
def test_rank_manager_integration(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    local_rank,
    node_rank,
    expect_parallel,
    clear_rank_env_vars,
):
    """Experiment should use parallel mode if RANK env vars are set and indicate not rank 0."""
    if local_rank is not None:
        os.environ["LOCAL_RANK"] = str(local_rank)
    if node_rank is not None:
        os.environ["NODE_RANK"] = str(node_rank)

    mock = mocker.patch.object(ArtifactManager, "__init__", return_value=None)
    try:
        run_experiment(experiment_name="test", parameters_list=["params1"])
    except AttributeError:
        # NOTE: I'm not actually sure a better way around this, all I want to test is that
        # manager was initialized with what I expect
        pass
    mock.assert_called_once_with(
        "test",
        store_entire_run=False,
        dry=False,
        dry_cache=False,
        custom_name=None,
        run_line="experiment test -p params1",
        parallel_lock=None,
        parallel_mode=expect_parallel,
        lazy=False,
        ignore_lazy=False,
        status_override=None,
        notes=None,
    )


def test_basic_params_get_loaded():
    """Loading from the two example parameter files (params1 and params2) should load a total of 3 args instances."""
    results, mngr = run_experiment("basic", ["params1", "params2"], dry=True)
    assert len(mngr.experiment_args_file_list) == 2
    total_args_count = 0
    for key in mngr.experiment_args:
        total_args_count += len(mngr.experiment_args[key])
    assert total_args_count == 3
    assert len(mngr.records) == 3


def test_appropriate_store_registry_use_dry(configuration, clear_filesystem):
    """Running an experiment in dry mode should not create a store or parameters registry."""
    results, mngr = run_experiment("basic", ["params1", "params2"], dry=True)
    assert not os.path.exists(f"{configuration['manager_cache_path']}/store.json")
    assert not os.path.exists(
        f"{configuration['manager_cache_path']}/params_registry.json"
    )


def test_appropriate_store_registry_use_wet(configuration, clear_filesystem):
    """Running an experiment NOT in dry mode SHOULD create a store and parameters registry."""
    results, mngr = run_experiment("basic", ["params1", "params2"], dry=False)
    assert os.path.exists(f"{configuration['manager_cache_path']}/store.json")
    assert os.path.exists(f"{configuration['manager_cache_path']}/params_registry.json")


# def test_parallel_calls_correct_ranges(mocker, parallel_count, expected_ranges):
def test_parallel_calls_count_correct(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
):
    """Running an experiment with three Args and with --parallel 3 should spawn 3 processes with the correct global index ranges."""
    mock = mocker.patch("multiprocessing.Process")
    mock.return_value.start = lambda: True
    mock.return_value.join = lambda: True
    mock_queue = mocker.patch("multiprocessing.Queue")
    mock_queue.return_value.get = lambda: [None, "success"]
    run_experiment("basic", ["params1", "params2"], parallel=3)
    assert mock.call_args_list[0].kwargs["args"][-9] == ["0-1"]
    assert mock.call_args_list[1].kwargs["args"][-9] == ["1-2"]
    assert mock.call_args_list[2].kwargs["args"][-9] == ["2-3"]
    assert mock.call_count == 3


def test_parallel_calls_count_correct_limits_threads(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
):
    """Running an experiment with more processes than args should still only spawn |args| number of processes."""
    mock = mocker.patch("multiprocessing.Process")
    mock.return_value.start = lambda: True
    mock.return_value.join = lambda: True
    mock_queue = mocker.patch("multiprocessing.Queue")
    mock_queue.return_value.get = lambda: [None, "success"]
    run_experiment("basic", ["params1", "params2"], parallel=4)
    assert mock.call_args_list[0].kwargs["args"][-9] == ["0-1"]
    assert mock.call_args_list[1].kwargs["args"][-9] == ["1-2"]
    assert mock.call_args_list[2].kwargs["args"][-9] == ["2-3"]
    assert mock.call_count == 3


# def test_parallel_calls_count_correct_ranges(
#     mocker,  # noqa: F811 -- mocker has to be passed in as fixture
# ):
#     mock = mocker.patch("multiprocessing.Process")
#     mock_queue = mocker.patch("multiprocessing.Queue")
#     mock_queue.return_value.get = lambda: [None, "success"]
#     run_experiment("basic", ["params1", "params2"], parallel=4)
#     print(mock.call_args_list)
#     assert mock.call_count == 3


def test_parallel_overwrite_removed_after_parallel(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
):
    """Using overwrite and parallel at the same time should pass overwrite to the subprocs, but not the main final run."""
    mock = mocker.patch("multiprocessing.Process")
    mock.return_value.start = lambda: True
    mock.return_value.join = lambda: True
    mock_queue = mocker.patch("multiprocessing.Queue")
    mock_queue.return_value.get = lambda: [None, "success"]
    results, mngr = run_experiment(
        "basic",
        ["params1", "params2"],
        stage_overwrites=["nonsense"],
        overwrite_override=True,
        parallel=1,
    )

    assert mock.call_args_list[0].kwargs["args"][2]  # overwrite_override
    assert mock.call_args_list[0].kwargs["args"][15] == ["nonsense"]

    # assert mngr.overwrite_stages = [] # NOTE: unclear if this is desired functionality or not
    for record in mngr.records:
        assert not record.args.overwrite


# TODO: do args_names/args_indices get correctly factored into parallel index calls
