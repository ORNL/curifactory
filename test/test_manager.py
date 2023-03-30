"""Testing pathing functions on the manager."""

import os

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory import ExperimentArgs, Record, aggregate, hashing, stage
from curifactory.caching import JsonCacher, Lazy, PickleCacher

# -----------------------------------------
# get_artifact_path unit tests
# -----------------------------------------


def test_get_path_basic(sample_args, configured_test_manager):
    """Calling get_artifact_path with a basic set of args should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_artifact_path("test_output", record)
    assert path == "test/examples/data/cache/test_sample_hash__test_output"


def test_get_path_basic_w_stagename(sample_args, configured_test_manager):
    """Calling get_artifact_path with a basic set of args and a valid stage name should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.current_stage_name = "somestage"
    path = configured_test_manager.get_artifact_path("test_output", record)
    assert path == "test/examples/data/cache/test_sample_hash_somestage_test_output"


def test_get_path_basic_w_custom_stagename(sample_args, configured_test_manager):
    """Calling get_artifact_path with a specific stage name should override the current stage name in the
    returned path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.current_stage_name = "somestage"
    path = configured_test_manager.get_artifact_path(
        "test_output", record, stage_name="someotherstage"
    )
    assert (
        path == "test/examples/data/cache/test_sample_hash_someotherstage_test_output"
    )


def test_get_path_subdir(sample_args, configured_test_manager):
    """Calling get_artifact_path with a basic set of args and a subdir should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_artifact_path(
        "test_output", record, subdir="WHAT"
    )
    assert path == "test/examples/data/cache/WHAT/test_sample_hash__test_output"


def test_get_path_subdirs(sample_args, configured_test_manager):
    """Calling get_artifact_path with a basic set of args and multiple subdirs should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_artifact_path(
        "test_output", record, subdir="WHAT/somethingelse"
    )
    assert (
        path
        == "test/examples/data/cache/WHAT/somethingelse/test_sample_hash__test_output"
    )


def test_get_path_prefix(sample_args, configured_test_manager):
    """Calling get_artifact_path with a basic set of args and a prefix should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    path = configured_test_manager.get_artifact_path(
        "test_output", record, prefix="special_data_proc"
    )
    assert path == "test/examples/data/cache/special_data_proc_sample_hash__test_output"


def test_get_path_store_full(sample_args, configured_test_manager):
    """Calling get_artifact_path with store-full should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.store_full = True
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_artifact_path("test_output", record, store=True)
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/artifacts/test_sample_hash__test_output"
    )


def test_get_path_custom_name(sample_args, configured_test_manager):
    """Calling get_artifact_path when a custom name is in use should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.prefix = "some_custom_name"
    path = configured_test_manager.get_artifact_path("test_output", record)
    assert path == "test/examples/data/cache/some_custom_name_sample_hash__test_output"


def test_get_path_custom_name_and_store_full(sample_args, configured_test_manager):
    """Calling get_artifact_path when a custom name is in use and storefull is called should return the expected path."""
    record = Record(configured_test_manager, sample_args)
    configured_test_manager.store_full = True
    configured_test_manager.prefix = "some_custom_name"
    ts = configured_test_manager.get_str_timestamp()
    path = configured_test_manager.get_artifact_path("test_output", record, store=True)
    assert (
        path
        == f"test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/artifacts/some_custom_name_sample_hash__test_output"
    )


def test_get_path_no_args(configured_test_manager):
    """Calling get_artifact_path with None args will result in None in the output name."""
    record = Record(configured_test_manager, None)
    path = configured_test_manager.get_artifact_path("test_output", record)
    assert path == f"test/examples/data/cache/test_{record.combo_hash}__test_output"


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
    configured_test_manager.store_full = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/artifacts --dry-cache"
    )


def test_run_line_sanitization_order(configured_test_manager):
    """The placement of the --store-full flag in the initial run line should not impact the reproduction line."""
    configured_test_manager.run_line = (
        "experiment test -p params1 --store-full --parallel 4"
    )
    configured_test_manager.store_full = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --parallel 4 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/artifacts --dry-cache"
    )


def test_run_line_sanitization_overwrite(configured_test_manager):
    """The reproduction line should not include overwrite."""
    configured_test_manager.run_line = (
        "experiment test -p params1 --store-full --parallel 4 --overwrite"
    )
    configured_test_manager.store_full = True
    configured_test_manager.store()
    ts = configured_test_manager.get_str_timestamp()
    assert (
        configured_test_manager.run_info["reproduce"]
        == f"experiment test -p params1 --parallel 4 --cache test/examples/data/runs/test_{configured_test_manager.experiment_run_number}_{ts}/artifacts --dry-cache"
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


# -----------------------------------------
# hash-setting tests
# -----------------------------------------


# TODO: (05/09/2022) with and without an agg of None args
def test_aggregate_stage_record_uses_combo_hash(configured_test_manager):
    """A combo hash for an aggregate should be stored on the record."""

    @stage(None, ["normal_hash"])
    def normal_stage(record):
        return record.args.hash

    @aggregate(["agg_hash"])
    def agg_stage(record, records):
        return record.args.hash

    r0 = Record(configured_test_manager, ExperimentArgs(name="test"))
    r0 = normal_stage(r0)

    # r1 = Record(configured_test_manager, None)
    r1 = Record(configured_test_manager, ExperimentArgs(name="test"))
    r1 = agg_stage(r1, [r0])

    assert r1.combo_hash is not None
    assert r1.combo_hash != r0.args.hash
    # TODO: move this to test_record


def test_stage_hash_after_aggregate_with_no_args(configured_test_manager):
    """Outputs from a normal stage after an aggregate stage with None arguments should be cached under the combo hash."""

    @aggregate(["testing"], [JsonCacher])
    def agg_stage(record, records):
        return "test"

    @stage(["testing"], ["testing2"], [JsonCacher])
    def normal_stage(record, testing):
        return "test2"

    r0 = Record(configured_test_manager, None)
    r1 = Record(configured_test_manager, ExperimentArgs(name="test"))

    r0 = normal_stage(agg_stage(r0, [r1]))

    combo_hash = hashing.add_args_combo_hash(r0, [r1], "", False)
    output_path_agg = os.path.join(
        configured_test_manager.cache_path, f"test_{combo_hash}_agg_stage_testing.json"
    )
    output_path_normal = os.path.join(
        configured_test_manager.cache_path,
        f"test_{combo_hash}_normal_stage_testing2.json",
    )

    assert os.path.exists(output_path_agg)
    assert os.path.exists(output_path_normal)
    # TODO: move this to test_record?
