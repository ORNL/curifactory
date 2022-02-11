"""Testing pathing functions on the manager."""

import os
from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory import stage, Record
from curifactory.caching import Cacheable, Lazy, PickleCacher


class FakeCacher(Cacheable):
    def __init__(self, path_override=None):
        super().__init__(".fake", path_override=path_override)

    def load(self):
        return None

    def save(self, obj):
        pass


# -----------------------------------------
# Stage/manager.get_path intergration tests
# -----------------------------------------


def test_stage_integration_basic(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    sample_args,
    configured_test_manager,
):
    """The stage should be calling manager's get_path with the correct parameters."""
    mock = mocker.patch.object(
        configured_test_manager, "get_path", return_value="test_path"
    )

    @stage([], ["test_output"], [FakeCacher])
    def do_thing(record):
        return "hello world"

    record = Record(configured_test_manager, sample_args)
    do_thing(record)
    mock.assert_called_once_with("test_output", record, aggregate_records=None)


def test_stage_integration_path_override(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    sample_args,
    configured_test_manager,
):
    """The stage should be calling manager's get_path with the correct parameters when using a path override in a cacher."""
    mock = mocker.patch.object(
        configured_test_manager, "get_path", return_value="test_path"
    )

    @stage([], ["test_output"], [FakeCacher(path_override="test/examples/WHAT")])
    def do_thing(record):
        return "hello world"

    record = Record(configured_test_manager, sample_args)
    do_thing(record)
    mock.assert_called_once_with(
        "test_output", record, base_path="test/examples/WHAT", aggregate_records=None
    )


def test_stage_integration_storefull(
    mocker,  # noqa: F811 -- mocker has to be passed in as fixture
    sample_args,
    configured_test_manager,
):
    """The stage should be calling manager's get_path twice with the correct parameters."""
    configured_test_manager.store_entire_run = True
    mock = mocker.patch.object(
        configured_test_manager, "get_path", return_value="test_path"
    )

    @stage([], ["test_output"], [FakeCacher])
    def do_thing(record):
        return "hello world"

    record = Record(configured_test_manager, sample_args)
    do_thing(record)

    assert len(mock.call_args_list) == 2
    assert mock.call_args_list[0].args == ("test_output", record)
    assert mock.call_args_list[0].kwargs == dict(aggregate_records=None)
    assert mock.call_args_list[1].args == ("test_output", record)
    assert mock.call_args_list[1].kwargs == dict(output=True, aggregate_records=None)


# -----------------------------------------
# get_path unit tests
# -----------------------------------------


def test_get_path_basic(sample_args, configured_test_manager):
    """Calling get_path with a basic set of args should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_path(
        "test_output", record, aggregate_records=None
    )
    assert path == "test/examples/data/cache/test_sample_hash__test_output"


def test_get_path_basic_w_stagename(sample_args, configured_test_manager):
    """Calling get_path with a basic set of args and a valid stage name should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.current_stage_name = "somestage"
    path = configured_test_manager.get_path(
        "test_output", record, aggregate_records=None
    )
    assert path == "test/examples/data/cache/test_sample_hash_somestage_test_output"


def test_get_path_path_override(sample_args, configured_test_manager):
    """Calling get_path with a basic set of args and a path override should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_path(
        "test_output", record, base_path="test/examples/WHAT", aggregate_records=None
    )
    assert path == "test/examples/WHAT/test_sample_hash__test_output"


def test_get_path_store_full(sample_args, configured_test_manager):
    """Calling get_path with store-full should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.store_entire_run = True
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_path(
        "test_output", record, output=True, aggregate_records=None
    )
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/test_sample_hash__test_output"
    )


def test_get_path_custom_name(sample_args, configured_test_manager):
    """Calling get_path when a custom name is in use should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.custom_name = "some_custom_name"
    path = configured_test_manager.get_path(
        "test_output", record, aggregate_records=None
    )
    assert path == "test/examples/data/cache/some_custom_name_sample_hash__test_output"


def test_get_path_custom_name_and_store_full(sample_args, configured_test_manager):
    """Calling get_path when a custom name is in use and storefull is called should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.store_entire_run = True
    configured_test_manager.custom_name = "some_custom_name"
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_path(
        "test_output", record, output=True, aggregate_records=None
    )
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/some_custom_name_sample_hash__test_output"
    )


def test_get_path_no_args(configured_test_manager):
    """Calling get_path with None args will result in None in the output name."""
    record = Record(configured_test_manager, None)
    path = configured_test_manager.get_path(
        "test_output", record, aggregate_records=None
    )
    assert path == "test/examples/data/cache/test_None__test_output"


# -----------------------------------------
# get_run_output_path unit tests
# -----------------------------------------


def test_get_run_output_path(configured_test_manager):
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_run_output_path()
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}"
    )


def test_get_run_output_path_w_obj_name(configured_test_manager):
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_run_output_path("testing_file.txt")
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/testing_file.txt"
    )
    assert os.path.exists(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}"
    )
    assert not os.path.isdir(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/testing_file.txt"
    )


def test_get_run_output_path_w_subdirs_obj_name(configured_test_manager):
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_run_output_path("subs/testing_file.txt")
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/subs/testing_file.txt"
    )
    assert os.path.exists(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/subs"
    )


# -----------------------------------------
# misc
# -----------------------------------------


def test_write_run_env_output(configured_test_manager):
    """Storing a manager run should output the four expected environment info textfiles into the store-full folder."""
    configured_test_manager.store()
    configured_test_manager.write_run_env_output()
    ts = configured_test_manager.get_str_timestamp()
    # NOTE: the run number is 1 because when we store it we actually populate that information (there's just a default value of 0)
    assert os.path.exists(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/requirements.txt"
    )
    assert os.path.exists(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/environment_meta.txt"
    )
    assert os.path.exists(
        f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/run_info.json"
    )


def test_run_line_sanitization_normal(configured_test_manager):
    """Ensure that a normal store-full run-line will result in a correct reproduction line in the run info."""
    configured_test_manager.run_line = "experiment test -p params1 --store-full"
    configured_test_manager.store_entire_run = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts} --dry-cache"
    )


def test_run_line_sanitization_order(configured_test_manager):
    """The placement of the --store-full flag in the initial run line should not impact the reproduction line."""
    configured_test_manager.run_line = (
        "experiment test -p params1 --store-full --parallel 4"
    )
    configured_test_manager.store_entire_run = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --parallel 4 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts} --dry-cache"
    )


def test_run_line_sanitization_overwrite(configured_test_manager):
    """The reproduction line should not include overwrite."""
    configured_test_manager.run_line = (
        "experiment test -p params1 --store-full --parallel 4 --overwrite"
    )
    configured_test_manager.store_entire_run = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --parallel 4 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts} --dry-cache"
    )


def test_cache_aware_dict_resolve(configured_test_manager):
    """Ensure when resolve is on, lazy objects in a record's state auto load the thing."""

    @stage([], [Lazy("tester")], cachers=[PickleCacher])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    output_stage(record)
    assert record.state["tester"] == "hello world"


def test_cache_aware_dict_no_resolve(configured_test_manager):
    """Ensure when resolve is off, lazy objects in a record's state remain lazy."""

    @stage([], [Lazy("tester")], cachers=[PickleCacher])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    output_stage(record)
    record.state.resolve = False
    assert type(record.state["tester"]) == Lazy
    assert record.state["tester"].name == "tester"
    assert type(record.state["tester"].cacher) == PickleCacher
