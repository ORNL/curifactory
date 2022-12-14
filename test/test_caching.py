import json
import os

import numpy as np
import pandas as pd
import pytest
from stages.cache_stages import filerefcacher_stage, filerefcacher_stage_multifile

import curifactory as cf
from curifactory.caching import PandasCsvCacher, PandasJsonCacher, PickleCacher
from curifactory.reporting import JsonReporter


# TODO: necessary? configured_test_manager already does this
@pytest.fixture()
def clear_stage_run(configured_test_manager):
    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")
    try:
        os.remove(ran_path)
    except FileNotFoundError:
        pass
    yield
    try:
        os.remove(ran_path)
    except FileNotFoundError:
        pass


def test_filerefcacher_stores_multiple_paths(configured_test_manager, clear_stage_run):
    """FileReferenceCacher should correctly store a list of files in the saved json."""
    r = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage_multifile(r)

    argshash = r.args.hash
    expected_list = [
        os.path.join(
            configured_test_manager.cache_path,
            f"test_{argshash}_filerefcacher_stage_multifile_my_files/thing{i}",
        )
        for i in range(5)
    ]

    with open(
        os.path.join(
            configured_test_manager.cache_path,
            f"test_{argshash}_filerefcacher_stage_multifile_output_paths.json",
        ),
    ) as infile:
        filelist = json.load(infile)
        assert filelist == expected_list

        for filename in filelist:
            assert os.path.exists(filename)


def test_filerefcacher_stores_single_path(configured_test_manager, clear_stage_run):
    r = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage(r)

    argshash = r.args.hash
    expected_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{argshash}_filerefcacher_stage_my_file",
    )

    with open(
        os.path.join(
            configured_test_manager.cache_path,
            f"test_{argshash}_filerefcacher_stage_output_path.json",
        ),
    ) as infile:
        filelist = json.load(infile)
        assert filelist == expected_path


def test_filerefcacher_shortcircuits(configured_test_manager, clear_stage_run):
    """FileReferenceCacher should short-circuit if all files in the filelist already exist."""
    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage_multifile(r0)

    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")
    assert os.path.exists(ran_path)
    os.remove(ran_path)

    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage_multifile(r1)
    assert not os.path.exists(ran_path)


def test_filerefcacher_runs_when_file_missing(configured_test_manager, clear_stage_run):
    """FileReferenceCacher should _not_ short-circuit if any of the files in the filelist are missing."""
    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage_multifile(r0)

    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")
    assert os.path.exists(ran_path)
    os.remove(ran_path)
    os.remove(
        os.path.join(
            configured_test_manager.cache_path,
            f"test_{r0.args.hash}_filerefcacher_stage_multifile_my_files/thing1",
        )
    )

    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    filerefcacher_stage_multifile(r1)
    assert os.path.exists(ran_path)


def test_reportables_are_cached(configured_test_manager):
    """Running a stage with a reportable should cache the reportable and a list of reportable cache files."""

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    basic_reportable(r0)

    list_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_basic_reportable_reportables_file_list.json",
    )

    reportable_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_basic_reportable_reportables/test_basic_reportable_0.pkl",
    )

    assert os.path.exists(list_path)

    with open(list_path) as infile:
        paths = json.load(infile)

    assert len(paths) == 1
    assert paths[0] == reportable_path
    assert os.path.exists(reportable_path)


def test_aggregate_reportables_are_cached(configured_test_manager):
    """Running an aggregate stage with a reportable should cache the reportable and a list of reportable cache files.
    (using the record's aggregate combo hash)"""

    @cf.aggregate(["test_output"], [PickleCacher])
    def basic_agg_reportable(record, records):
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    print("hash", r0.args.hash)
    basic_agg_reportable(r0)
    print("hash", r0.args.hash)
    assert r0.args.hash is not None

    list_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.combo_hash}_basic_agg_reportable_reportables_file_list.json",
    )

    reportable_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.combo_hash}_basic_agg_reportable_reportables/(Aggregate)_test_basic_agg_reportable_0.pkl",
    )

    print([thing for thing in os.listdir(configured_test_manager.cache_path)])
    print("---")
    print(list_path)
    print(reportable_path)

    assert os.path.exists(list_path)

    with open(list_path) as infile:
        paths = json.load(infile)

    assert len(paths) == 1
    print("PATHS:", paths)
    assert paths[0] == reportable_path
    assert os.path.exists(reportable_path)


# TODO: test that those reportables are correctly reloaded when re-run


# def test_reportables_are_cached_with_store_full(configured_test_manager):
#     pass


def test_aggregate_args_no_records_loads_cache(configured_test_manager):
    """Calling an aggregate stage with valid args, twice, should load from cache and not execute."""
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r0 = test_agg(r0, [])
    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r1 = test_agg(r1, [])

    assert call_count == 1
    assert r1.state["test_output"] == "hello world!"


def test_aggregate_args_records_loads_cache(configured_test_manager):
    """Calling an aggregate stage with valid args, twice, with other non-overwrite records involved
    should load from cache and not execute."""
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testA"))
    rB = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testB"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 1
    assert r1.state["test_output"] == "hello world!"


def test_aggregate_args_overwrite_no_records_doesnot_load_cache(
    configured_test_manager,
):
    """Calling an aggregate stage with valid args with overwrite specified, twice, should NOT load
    from cache and execute."""
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    r0 = cf.Record(
        configured_test_manager, cf.ExperimentArgs(name="test", overwrite=True)
    )
    r0 = test_agg(r0, [])
    r1 = cf.Record(
        configured_test_manager, cf.ExperimentArgs(name="test", overwrite=True)
    )
    r1 = test_agg(r1, [])

    assert call_count == 2


def test_aggregate_args_records_overwrite_loads_cache(configured_test_manager):
    """Calling an aggregate stage with valid args, twice, with other records with overwrite
    should still load from cache and not execute.

    This is a weird edge case, running with the experiment CLI should ensure this doesn't happen
    (since --overwrite will apply to all args, it's set on an artifactmanager-level.) This could in
    principle only happen in a live context (like a notebook).

    The expected behavior, given that we have no intelligent-DAG-based-overwrites yet, is to use the
    cache anyway. The only reason we check the input records in other cases is when the agg stage record
    has no arguments of its own and so overwrite must be inferred. In this case however, we have an actual
    set of arguments to use, so there's no way to distinguish between whether an overwrite of False is
    "default" or intentional, so we just assume we trust that the args are correct.
    """
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(
        configured_test_manager, cf.ExperimentArgs(name="testA", overwrite=True)
    )
    rB = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testB"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 1


def test_aggregate_no_args_no_records_doesnot_load_cache(configured_test_manager):
    """Calling an aggregate stage with no args, twice, should NOT load from cache and execute.

    This is a relatively pointless situation, but just to cover the bases and establish expected functionality,
    a no args situation should not use the cache when no other records present, as we have no reasonable
    combo hash and no information about whether overwrite is specified on anything else or not.
    """
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    r0 = cf.Record(configured_test_manager, None)
    r0 = test_agg(r0, [])
    r1 = cf.Record(configured_test_manager, None)
    r1 = test_agg(r1, [])

    assert call_count == 2


def test_aggregate_no_args_records_loads_cache(configured_test_manager):
    """Calling an aggregate stage with no args, twice, with other records should load from cache and not execute.

    Even though there's no args, we can establish a re-execution based on the combohash of the passed records, so
    allow cache usage.
    """
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testA"))
    rB = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testB"))

    r0 = cf.Record(configured_test_manager, None)
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, None)
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 1
    assert r1.state["test_output"] == "hello world!"


# TODO: (05/13/2022) what about stages after such an agg? Without global overwrite specified, they won't overwrite, since
# it's not part of an args. This is the same problem as giving an --overwrite-stage though, so unsure that this needs to be
# handled. The below test case can really only apply if you're manually doing weird things outside of experiment CLI
def test_aggregate_no_args_records_overwrite_doesnot_load_cache(
    configured_test_manager,
):
    """Calling an aggregate stage with no args, twice, with other records with overwrite should NOT load from
    cache and execute.

    If at least one of the associated records has overwrite specified, that should carry through into
    """
    call_count = 0

    @cf.aggregate(["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(
        configured_test_manager, cf.ExperimentArgs(name="testA", overwrite=True)
    )
    rB = cf.Record(configured_test_manager, cf.ExperimentArgs(name="testB"))

    r0 = cf.Record(configured_test_manager, None)
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, None)
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 2


def test_get_path_file_included_in_full_store(configured_test_manager):
    """A file manually saved within a stage using get_path should correctly be
    copied to the run folder in a full-store run."""
    configured_test_manager.store_entire_run = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_path("my_extra_file.txt")
        with open(path, "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_custom_output_my_extra_file.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path, f"test_{r0.args.hash}_custom_output_my_extra_file.txt"
    )
    assert os.path.exists(regular_custom_output_path)
    assert os.path.exists(full_store_custom_output_path)


def test_get_dir_folder_included_in_full_store(configured_test_manager):
    """File(s) manually saved within a stage using get_dir should correctly be
    copied to the run folder in a full-store run."""
    configured_test_manager.store_entire_run = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_dir("my_extra_dir")
        with open(f"{path}/testfile.txt", "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path,
        f"test_{r0.args.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    assert os.path.exists(regular_custom_output_path)
    assert os.path.exists(full_store_custom_output_path)


def test_get_path_file_excluded_in_full_store_when_not_tracked(configured_test_manager):
    """A file manually saved within a stage using get_path should NOT be
    copied to the run folder in a full-store run when not tracked."""
    configured_test_manager.store_entire_run = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_path("my_extra_file.txt", False)
        with open(path, "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_custom_output_my_extra_file.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path, f"test_{r0.args.hash}_custom_output_my_extra_file.txt"
    )
    assert os.path.exists(regular_custom_output_path)
    assert not os.path.exists(full_store_custom_output_path)


def test_get_dir_folder_excluded_in_full_store_when_not_tracked(
    configured_test_manager,
):
    """File(s) manually saved within a stage using get_dir should NOT be
    copied to the run folder in a full-store run when not tracked."""
    configured_test_manager.store_entire_run = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_dir("my_extra_dir", False)
        with open(f"{path}/testfile.txt", "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path,
        f"test_{r0.args.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    assert os.path.exists(regular_custom_output_path)
    assert not os.path.exists(full_store_custom_output_path)


def test_pandas_csv_cacher_with_df_with_comma(configured_test_manager):
    """The PandasCSVCacher shouldn't fail when given a dataframe containing a comma."""

    @cf.stage(None, ["output"], [PandasCsvCacher])
    def save_comma_df(record):
        data = {
            "col1": ["things, with commas"],
            "col2": ['other "possible breaking," things'],
        }
        df = pd.DataFrame(data=data)
        return df

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    save_comma_df(r0)

    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    save_comma_df(r1)

    df1 = r0.state["output"]
    df2 = r1.state["output"]

    assert list(df1.columns) == list(df2.columns)
    assert df1.to_dict() == df2.to_dict()


def test_pandas_json_cacher_with_df_no_recursion_error(configured_test_manager):
    """Regression test for weird bug in #3, caching a df with 17+ cols and 5+
    rows with the pandasjsoncacher shouldn't crash with a maximum recursion
    level reached."""

    data = np.random.rand(18, 6)

    @cf.stage(None, ["output"], [PandasJsonCacher])
    def save_large_df(record):
        df = pd.DataFrame(data)
        return df

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    save_large_df(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_save_large_df_output.json",
    )

    assert os.path.exists(path)
    df = pd.read_json(path)
    np.testing.assert_almost_equal(df.values, data)
