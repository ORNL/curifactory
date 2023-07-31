import json
import os
from dataclasses import dataclass
from test.examples.stages.cache_stages import (
    filerefcacher_stage,
    filerefcacher_stage_multifile,
)

import numpy as np
import pandas as pd
import pytest

import curifactory as cf
from curifactory.caching import (
    Cacheable,
    JsonCacher,
    PandasCacher,
    PandasCsvCacher,
    PandasJsonCacher,
    PickleCacher,
    RawJupyterNotebookCacher,
    _PandasIOType,
)
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
    r = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage_multifile(r)

    argshash = r.params.hash
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
    r = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage(r)

    argshash = r.params.hash
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
    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage_multifile(r0)

    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")
    assert os.path.exists(ran_path)
    os.remove(ran_path)

    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage_multifile(r1)
    assert not os.path.exists(ran_path)


def test_filerefcacher_runs_when_file_missing(configured_test_manager, clear_stage_run):
    """FileReferenceCacher should _not_ short-circuit if any of the files in the filelist are missing."""
    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage_multifile(r0)

    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")
    assert os.path.exists(ran_path)
    os.remove(ran_path)
    os.remove(
        os.path.join(
            configured_test_manager.cache_path,
            f"test_{r0.params.hash}_filerefcacher_stage_multifile_my_files/thing1",
        )
    )

    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    filerefcacher_stage_multifile(r1)
    assert os.path.exists(ran_path)


def test_reportables_are_cached(configured_test_manager):
    """Running a stage with a reportable should cache the reportable and a list of reportable cache files."""

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r0)

    list_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_basic_reportable_reportables_file_list.json",
    )

    reportable_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_basic_reportable_reportables/test_basic_reportable_0.pkl",
    )

    assert os.path.exists(list_path)

    with open(list_path) as infile:
        paths = json.load(infile)

    assert len(paths) == 1
    assert paths[0] == reportable_path
    assert os.path.exists(reportable_path)


def test_named_reportables_are_cached(configured_test_manager):
    """Running a stage with a named reportable should cache the reportable and a list of reportable cache files."""

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        record.report(JsonReporter({"test": "hello world"}, name="thing"))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r0)

    list_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_basic_reportable_reportables_file_list.json",
    )

    reportable_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_basic_reportable_reportables/test_basic_reportable_thing.pkl",
    )

    assert os.path.exists(list_path)

    with open(list_path) as infile:
        paths = json.load(infile)

    assert len(paths) == 1
    assert paths[0] == reportable_path
    assert os.path.exists(reportable_path)


def test_cached_reportables_loaded_without_doubling_name(configured_test_manager):
    """Re-loading cached reportables should not double name!

    (This was caused previously by re-reporting on the record, which prefixed the
    name in-place.)
    """
    run_count = 0

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        nonlocal run_count
        run_count += 1
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r0)

    assert len(configured_test_manager.reportables) == 1

    # run again in a new record with exact same config, so it will find cached
    # things.
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r1)

    # make sure we didn't run the stage, so we actually had to load reportables
    assert run_count == 1

    assert len(configured_test_manager.reportables) == 2
    assert configured_test_manager.reportables[0].name is None
    assert configured_test_manager.reportables[1].name is None
    assert (
        configured_test_manager.reportables[0].qualified_name
        == "test_basic_reportable_0"
    )
    assert (
        configured_test_manager.reportables[1].qualified_name
        == "test_basic_reportable_1"
    )


def test_cached_named_reportables_loaded_without_doubling_name(configured_test_manager):
    """Re-loading cached named reportables should not double name!

    (This was caused previously by re-reporting on the record, which prefixed the
    name in-place.)
    """
    run_count = 0

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        nonlocal run_count
        run_count += 1
        record.report(JsonReporter({"test": "hello world"}, name="thing"))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r0)

    assert len(configured_test_manager.reportables) == 1

    # run again in a new record with exact same config, so it will find cached
    # things.
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r1)

    # make sure we didn't run the stage, so we actually had to load reportables
    assert run_count == 1

    assert len(configured_test_manager.reportables) == 2
    assert (
        configured_test_manager.reportables[0].name
        == configured_test_manager.reportables[1].name
    )
    assert (
        configured_test_manager.reportables[0].qualified_name
        == configured_test_manager.reportables[1].qualified_name
    )


def test_aggregate_reportables_are_cached(configured_test_manager):
    """Running an aggregate stage with a reportable should cache the reportable and a list of reportable cache files.
    (using the record's aggregate combo hash)"""

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def basic_agg_reportable(record, records):
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    print("hash", r0.params.hash)
    basic_agg_reportable(r0)
    print("hash", r0.params.hash)
    assert r0.params.hash is not None

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

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r0 = test_agg(r0, [])
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = test_agg(r1, [])

    assert call_count == 1
    assert r1.state["test_output"] == "hello world!"


def test_aggregate_args_records_loads_cache(configured_test_manager):
    """Calling an aggregate stage with valid args, twice, with other non-overwrite records involved
    should load from cache and not execute."""
    call_count = 0

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testA"))
    rB = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testB"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 1
    assert r1.state["test_output"] == "hello world!"


def test_aggregate_args_overwrite_no_records_doesnot_load_cache(
    configured_test_manager,
):
    """Calling an aggregate stage with valid args with overwrite specified, twice, should NOT load
    from cache and execute."""
    call_count = 0

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    r0 = cf.Record(
        configured_test_manager, cf.ExperimentParameters(name="test", overwrite=True)
    )
    r0 = test_agg(r0, [])
    r1 = cf.Record(
        configured_test_manager, cf.ExperimentParameters(name="test", overwrite=True)
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

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(
        configured_test_manager, cf.ExperimentParameters(name="testA", overwrite=True)
    )
    rB = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testB"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 1


def test_aggregate_no_args_no_records_doesnot_load_cache(configured_test_manager):
    """Calling an aggregate stage with no args, twice, should NOT load from cache and execute.

    This is a relatively pointless situation, but just to cover the bases and establish expected functionality,
    a no args situation should not use the cache when no other records present, as we have no reasonable
    combo hash and no information about whether overwrite is specified on anything else or not.
    """
    call_count = 0

    @cf.aggregate(None, ["test_output"], [PickleCacher])
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

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testA"))
    rB = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testB"))

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

    @cf.aggregate(None, ["test_output"], [PickleCacher])
    def test_agg(record, records):
        nonlocal call_count
        call_count += 1
        return "hello world!"

    rA = cf.Record(
        configured_test_manager, cf.ExperimentParameters(name="testA", overwrite=True)
    )
    rB = cf.Record(configured_test_manager, cf.ExperimentParameters(name="testB"))

    r0 = cf.Record(configured_test_manager, None)
    r0 = test_agg(r0, [rA, rB])
    r1 = cf.Record(configured_test_manager, None)
    r1 = test_agg(r1, [rA, rB])

    assert call_count == 2


def test_get_path_file_included_in_full_store(configured_test_manager):
    """A file manually saved within a stage using get_path should correctly be
    copied to the run folder in a full-store run."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_path("my_extra_file.txt")
        with open(path, "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_custom_output_my_extra_file.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path, f"test_{r0.params.hash}_custom_output_my_extra_file.txt"
    )
    assert os.path.exists(regular_custom_output_path)
    assert os.path.exists(full_store_custom_output_path)


def test_get_dir_folder_included_in_full_store(configured_test_manager):
    """File(s) manually saved within a stage using get_dir should correctly be
    copied to the run folder in a full-store run."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_dir("my_extra_dir")
        with open(f"{path}/testfile.txt", "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    assert os.path.exists(regular_custom_output_path)
    assert os.path.exists(full_store_custom_output_path)


def test_get_path_file_excluded_in_full_store_when_not_tracked(configured_test_manager):
    """A file manually saved within a stage using get_path should NOT be
    copied to the run folder in a full-store run when not tracked."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_path("my_extra_file.txt", track=False)
        with open(path, "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_custom_output_my_extra_file.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path, f"test_{r0.params.hash}_custom_output_my_extra_file.txt"
    )
    assert os.path.exists(regular_custom_output_path)
    assert not os.path.exists(full_store_custom_output_path)


def test_get_dir_folder_excluded_in_full_store_when_not_tracked(
    configured_test_manager,
):
    """File(s) manually saved within a stage using get_dir should NOT be
    copied to the run folder in a full-store run when not tracked."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["other_output"], [PickleCacher])
    def custom_output(record):
        path = record.get_dir("my_extra_dir", track=False)
        with open(f"{path}/testfile.txt", "w") as outfile:
            outfile.write("Hello world!")

        return 13

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    custom_output(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    regular_custom_output_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_custom_output_my_extra_dir/" "testfile.txt",
    )
    full_store_custom_output_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_custom_output_my_extra_dir/" "testfile.txt",
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

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    save_comma_df(r0)

    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
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

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    save_large_df(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_save_large_df_output.json",
    )

    assert os.path.exists(path)
    df = pd.read_json(path)
    np.testing.assert_almost_equal(df.values, data)


@pytest.mark.parametrize(
    "io_format", ["csv", "json", "parquet", "pickle", "orc", "hdf5", "excel", "xml"]
)
def test_pandas_cacher_for_all_io_formats(configured_test_manager, io_format):
    """The PandasCacher should work for save and load for all IO formats."""

    io_format_enum = _PandasIOType[io_format]
    data = {
        "col1": ["things, with commas", "more rows", "MOAR!"],
        "col2": ['other "possible breaking," things', "Tres Commas", "No"],
        "col3": [42, -1, 3.14159],
    }
    saved_df = pd.DataFrame(data)

    @cf.stage(outputs=["df"], cachers=[PandasCacher(format=io_format)])
    def write_pandas(record):
        return saved_df

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    write_pandas(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_write_pandas_df",
    )
    assert os.path.exists(f"{path}.{io_format_enum.value}")

    loaded_df = PandasCacher(f"{path}.{io_format_enum.value}", format=io_format).load()

    assert saved_df.equals(loaded_df)


@pytest.mark.parametrize(
    # fmt: off
    "io_format,to_args,read_args",
    [
        ("csv", {}, {"index_col": 0, "dtype_backend": "pyarrow"}),
        ("json", {"double_precision": 15}, {"dtype_backend": "pyarrow"}),
        ("parquet", {}, {"dtype_backend": "pyarrow"}),
        ("pickle", {}, {}),
        ("orc", {}, {"dtype_backend": "pyarrow"}),
        ("excel", {}, {"index_col": 0, "dtype_backend": "pyarrow"}),
        ("xml", {"index": False}, {"dtype_backend": "pyarrow"}),
    ]
    # fmt: on
)
def test_pandas_cacher_for_all_io_formats_with_args(
    configured_test_manager, io_format, to_args, read_args
):
    """The PandasCacher should work for save and load for all IO formats
    with input to_args and read_args."""

    io_format_enum = _PandasIOType[io_format]
    data = {
        "col1": ["things, with commas", "more rows", "MOAR!"],
        "col2": ['other "possible breaking," things', "Tres Commas", "No"],
        "col3": [42, -1, 3.14159],
    }
    saved_df = pd.DataFrame(data)
    saved_df = saved_df.convert_dtypes(dtype_backend="pyarrow")
    if io_format_enum in (_PandasIOType.csv, _PandasIOType.excel):
        saved_df.index = saved_df.index.astype("int64[pyarrow]", copy=False)

    @cf.stage(
        outputs=["df"],
        cachers=[PandasCacher(format=io_format, to_args=to_args, read_args=read_args)],
    )
    def write_pandas(record):
        return saved_df

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    write_pandas(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_write_pandas_df",
    )
    assert os.path.exists(f"{path}.{io_format_enum.value}")

    loaded_df = PandasCacher(
        f"{path}.{io_format_enum.value}",
        format=io_format,
        to_args=to_args,
        read_args=read_args,
    ).load()

    assert saved_df.equals(loaded_df)


@pytest.mark.parametrize(
    # fmt: off
    "cacher_args,suffix,expected_path",
    [
        (dict(name="test"), None, "test_hash_test_stage_test.pkl"),
        (dict(name="test"), "_metadata.json", "test_hash_test_stage_test_metadata.json"),
        (dict(name="test"), "_thing", "test_hash_test_stage_test_thing"),
        (dict(name="test.pkl"), None, "test_hash_test_stage_test.pkl"),
        (dict(path_override="test/examples/data/cache/test"), None, "test"),
        (dict(path_override="test/examples/data/cache/test.pkl"), None, "test.pkl"),
        (dict(path_override="test/examples/data/cache/test"), "_metadata.json", "test_metadata.json"),
        (dict(path_override="test/examples/data/cache/test.pkl"), "_metadata.json", "test_metadata.json"),
        (dict(name="test", prefix="someprefix"), None, "someprefix_hash_test_stage_test.pkl"),
        (dict(name="test", prefix="someprefix"), "_metadata.json", "someprefix_hash_test_stage_test_metadata.json"),
        (dict(name="test", subdir="01_raw"), None, "01_raw/test_hash_test_stage_test.pkl"),
        (dict(name="test", subdir="01_raw"), "_metadata.json", "01_raw/test_hash_test_stage_test_metadata.json"),
        (dict(name="test", subdir="01_raw", prefix="someprefix"), None, "01_raw/someprefix_hash_test_stage_test.pkl"),
        (dict(name="test", subdir="01_raw", prefix="someprefix"), "_metadata.json", "01_raw/someprefix_hash_test_stage_test_metadata.json"),
    ]
    # fmt: on
)
def test_cacheable_get_path(
    configured_test_manager, cacher_args, suffix, expected_path
):
    """A cacher's get_path should correctly handle different combinations of path inputs and
    requested suffixes."""
    configured_test_manager.current_stage_name = "test_stage"
    r = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r.params.hash = "hash"

    cacher = PickleCacher(**cacher_args, record=r)

    path_prefix = "test/examples/data/cache/"
    path = cacher.get_path(suffix)
    assert path == path_prefix + expected_path


def test_cacher_outputs_metadata(configured_test_manager):
    """A basic cacher output should also output a metadata file associated with it."""

    @cf.stage(None, ["output"], [PickleCacher])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_output_thing_output.pkl",
    )
    metadata_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_output_thing_output_metadata.json",
    )

    assert os.path.exists(path)
    assert os.path.exists(metadata_path)


def test_cacher_outputs_metadata_storefull(configured_test_manager):
    """A cacher output should copy the associated metadata file to the full store if full store mode."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["output"], [PickleCacher])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    metadata_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_output_thing_output_metadata.json",
    )
    assert os.path.exists(metadata_path)


def test_manual_static_path_cacher_outputs_metadata(configured_test_manager):
    """Metadata should still output at the correct path when using a manual static-path cacher."""

    @cf.stage()
    def output_thing(record):
        cacher = PickleCacher(
            "test/examples/data/cache/raw_path_file.pkl", record=record
        )
        cacher.save("hello world")
        cacher.save_metadata()

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    path = "test/examples/data/cache/raw_path_file.pkl"
    loader = PickleCacher(path)
    metadata = loader.load_metadata()

    assert os.path.exists(path)
    assert os.path.exists("test/examples/data/cache/raw_path_file_metadata.json")
    assert loader.load() == "hello world"
    assert metadata["stage"] == "output_thing"


def test_load_metadata_with_manual_cacher_from_stage_cacher_path(
    configured_test_manager,
):
    """Metadata for a static-path cacher created based on a stage cacher's path should still be loadable."""

    @cf.stage(None, ["output"], [PickleCacher])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_output_thing_output.pkl",
    )

    manual_cacher = PickleCacher(path)
    metadata = manual_cacher.load_metadata()

    assert metadata is not None
    assert metadata["artifact_name"] == "output"


def test_overwrites_stage_doesnot_break_storefull_of_other_stages(
    configured_test_manager, alternate_test_manager2
):
    """An experiment run twice, the second time with an overwrite-stage flag and store-full, should
    transfer both the newly overwritten artifacts into the run folder as well as the old non-overwritten
    artifacts from the other stages."""
    configured_test_manager.store_full = True
    alternate_test_manager2.store_full = True
    alternate_test_manager2.overwrite_stages = ["overwritten_output"]

    nonoverwritten_call_count = 0
    overwritten_call_count = 0

    @cf.stage(None, ["firstoutput"], [PickleCacher(prefix="common")])
    def non_overwritten_output(record):
        nonlocal nonoverwritten_call_count
        nonoverwritten_call_count += 1
        return "hello!"

    @cf.stage(["firstoutput"], ["secondoutput"], [PickleCacher(prefix="common")])
    def overwritten_output(record, firstoutput):
        nonlocal overwritten_call_count
        overwritten_call_count += 1
        return "world!"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = cf.Record(alternate_test_manager2, cf.ExperimentParameters(name="test2"))

    overwritten_output(non_overwritten_output(r0))
    overwritten_output(non_overwritten_output(r1))

    assert nonoverwritten_call_count == 1
    assert overwritten_call_count == 2

    second_full_store_path = f"{alternate_test_manager2.runs_path}/test2_1_{alternate_test_manager2.get_str_timestamp()}/artifacts"
    nonoverwritten_output_path = os.path.join(
        second_full_store_path,
        f"common_{r1.params.hash}_non_overwritten_output_firstoutput_metadata.json",
    )
    overwritten_output_path = os.path.join(
        second_full_store_path,
        f"common_{r1.params.hash}_overwritten_output_secondoutput_metadata.json",
    )

    assert os.path.exists(nonoverwritten_output_path)
    assert os.path.exists(overwritten_output_path)


def test_non_tracked_cacher_does_not_copy_metadata_to_full_store(
    configured_test_manager,
):
    """A non-tracked cacher should not copy the metadata file to the full store."""
    configured_test_manager.store_full = True

    @cf.stage(None, ["output"], [PickleCacher(track=False)])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    metadata_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_output_thing_output_metadata.json",
    )
    assert not os.path.exists(metadata_path)


def test_no_metadata_written_to_dry_cache_folder(
    configured_test_manager,
):
    """Metadata should not be written out to a dry-cache cache folder."""
    configured_test_manager.dry_cache = True

    @cf.stage(None, ["output"], [PickleCacher])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"

    metadata_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_output_thing_output_metadata.json",
    )
    assert not os.path.exists(metadata_path)


def test_existing_metadata_not_overwritten_when_cache_used(
    configured_test_manager, alternate_test_manager2
):
    """When cached values loaded in, existing metadata file should not be overwritten. Tested here
    with cross-caching"""

    @cf.stage(None, ["output"], [PickleCacher(prefix="commondata")])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    r1 = cf.Record(alternate_test_manager2, cf.ExperimentParameters(name="test"))
    output_thing(r1)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"commondata_{r1.params.hash}_output_thing_output_metadata.json",
    )
    metadata = JsonCacher(path).load()
    assert (
        metadata["manager_run_info"]["experiment_name"] == "test"
    )  # rather than test2


def test_uses_existing_metadata_in_full_store_when_cache_used(
    configured_test_manager, alternate_test_manager2
):
    """A full store output that's using a cached value should transfer the _existing_ metadata file
    to the full store."""
    configured_test_manager.store_full = True
    alternate_test_manager2.store_full = True

    @cf.stage(None, ["output"], [PickleCacher(prefix="commondata")])
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    r1 = cf.Record(alternate_test_manager2, cf.ExperimentParameters(name="test"))
    output_thing(r1)

    full_store_path = f"{alternate_test_manager2.runs_path}/test2_1_{alternate_test_manager2.get_str_timestamp()}/artifacts"
    path = os.path.join(
        full_store_path,
        f"commondata_{r1.params.hash}_output_thing_output_metadata.json",
    )
    metadata = JsonCacher(path).load()
    assert (
        metadata["manager_run_info"]["experiment_name"] == "test"
    )  # rather than test2


def test_cacher_getpath_keeps_stagename_after_later_stages(configured_test_manager):
    """A cacher created in one stage should still return the same get_paths even after later
    stages have executed."""
    cacher = PickleCacher()

    @cf.stage(None, ["output"], [cacher])
    def output_thing(record):
        return "Hello world"

    @cf.stage(["output"], ["output2"])
    def do_something_else(record, output):
        return output + ", kthxbye"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r0 = output_thing(r0)
    assert cacher.stage == "output_thing"
    first_path = cacher.get_path()

    do_something_else(r0)
    assert cacher.stage == "output_thing"
    second_path = cacher.get_path()

    assert first_path == second_path


def test_path_override_cacher_saves_to_that_path(configured_test_manager):
    """A cacher with path-override set should save the output to that path."""

    @cf.stage(
        None, ["output"], [PickleCacher("test/examples/data/cache/raw_path_file.pkl")]
    )
    def output_thing(record):
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    path = "test/examples/data/cache/raw_path_file.pkl"
    loader = PickleCacher(path)
    metadata = loader.load_metadata()

    assert os.path.exists(path)
    assert os.path.exists("test/examples/data/cache/raw_path_file_metadata.json")
    assert loader.load() == "Hello world"
    assert metadata["stage"] == "output_thing"


def test_separate_managers_no_crosscache_by_default(
    configured_test_manager, alternate_test_manager2
):
    """Two separate managers with different paths and a common stage withOUT custom prefix should
    _not_ use the same cached value."""
    run_count = 0

    @cf.stage(None, ["output"], [PickleCacher])
    def output_thing(record):
        nonlocal run_count
        run_count += 1
        return "Hello world"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = cf.Record(alternate_test_manager2, cf.ExperimentParameters(name="test"))
    output_thing(r0)
    output_thing(r1)
    assert run_count == 2


def test_separate_managers_common_prefix_cacher_crosscaches(
    configured_test_manager, alternate_test_manager2
):
    """Two separate managers with different paths but a common stage with custom prefix should
    both use the same cached value if the args are the same."""
    run_count = 0

    @dataclass
    class MyArgs(cf.ExperimentParameters):
        a: int = 5

    @cf.stage(None, ["output"], [PickleCacher(prefix="commondata")])
    def output_thing(record):
        nonlocal run_count
        run_count += 1
        return "Hello world"

    r0 = cf.Record(configured_test_manager, MyArgs(name="test", a=4))
    r1 = cf.Record(alternate_test_manager2, MyArgs(name="test2", a=4))
    output_thing(r0)
    output_thing(r1)
    assert run_count == 1


def test_separate_managers_common_prefix_cacher_no_crosscache_if_args_diff(
    configured_test_manager, alternate_test_manager2
):
    """Two separate managers with different paths but a common stage with custom prefix should
    _not_ use the same cached value if the args are not the same."""
    run_count = 0

    @dataclass
    class MyArgs(cf.ExperimentParameters):
        a: int = 5

    @cf.stage(None, ["output"], [PickleCacher(prefix="commondata")])
    def output_thing(record):
        nonlocal run_count
        run_count += 1
        return "Hello world"

    r0 = cf.Record(configured_test_manager, MyArgs(name="test", a=4))
    r1 = cf.Record(alternate_test_manager2, MyArgs(name="test2", a=5))
    output_thing(r0)
    output_thing(r1)
    assert run_count == 2


def test_cacher_with_record_get_path(configured_test_manager):
    """A manual cacher with record.get_path static path should correctly save and load to that path."""
    cacher = None

    @cf.stage()
    def manual_output_thing(record):
        nonlocal cacher
        cacher = JsonCacher(record.get_path("manualtest.json"))
        cacher.save(dict(message="hello world"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    manual_output_thing(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_manual_output_thing_manualtest.json",
    )
    assert os.path.exists(path)
    assert cacher.load()["message"] == "hello world"


def test_cacher_with_record_get_path_no_extension(configured_test_manager):
    """A manual cacher with record.get_path static path should correctly save and load to that path,
    even when an extension hasn't been implicitly provided in the record.get_path call
    """
    cacher = None

    @cf.stage()
    def manual_output_thing(record):
        nonlocal cacher
        cacher = JsonCacher(record.get_path("manualtest"))
        cacher.save(dict(message="hello world"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    manual_output_thing(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_manual_output_thing_manualtest",
    )
    assert os.path.exists(path)
    assert cacher.load()["message"] == "hello world"


def test_cacher_with_record_get_path_full_store(configured_test_manager):
    """A manual cacher with record.get_path static path should correctly store to that path in
    full store in full store mode."""
    configured_test_manager.store_full = True

    @cf.stage()
    def manual_output_thing(record):
        cacher = JsonCacher(record.get_path("manualtest.json"))
        cacher.save(dict(message="hello world"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    manual_output_thing(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"
    path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_manual_output_thing_manualtest.json",
    )
    assert os.path.exists(path)


def test_cacher_with_record_get_path_no_extension_full_store(configured_test_manager):
    """A manual cacher with record.get_path static path should correctly store to that path in
    full store in full store mode, even when an extension hasn't been implicitly provided to the
    record.get_path"""
    configured_test_manager.store_full = True
    cacher = None

    @cf.stage()
    def manual_output_thing(record):
        nonlocal cacher
        cacher = JsonCacher(record.get_path("manualtest"))
        cacher.save(dict(message="hello world"))

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    manual_output_thing(r0)

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"
    path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_manual_output_thing_manualtest",
    )
    assert os.path.exists(path)


def test_custom_cacher_using_get_dir_store_full(configured_test_manager):
    """A custom cacheable that uses the cacher's get_dir function should correctly create
    the directory and allow storing in it, and transfer it to a full store."""
    configured_test_manager.store_full = True

    class MultiCacher(Cacheable):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def save(self, obj):
            dirpath = self.get_dir()
            with open(f"{dirpath}/thing.json", "w") as outfile:
                json.dump(obj, outfile)
            with open(f"{dirpath}/what.txt", "w") as outfile:
                outfile.write("This is the confirmation that thing.json was written.")

        def load(self):
            dirpath = self.get_dir()
            with open(f"{dirpath}/thing.json") as infile:
                return json.load(infile)

    cacher = MultiCacher()

    @cf.stage(outputs=["output"], cachers=[cacher])
    def output_thing(record):
        return dict(message="hello world!")

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    output_thing(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_output_thing_output",
    )
    assert os.path.exists(path)
    assert os.path.exists(f"{path}/thing.json")
    assert os.path.exists(f"{path}/what.txt")

    full_store_path = f"{configured_test_manager.runs_path}/test_1_{configured_test_manager.get_str_timestamp()}/artifacts"
    full_path = os.path.join(
        full_store_path,
        f"test_{r0.params.hash}_output_thing_output",
    )
    assert os.path.exists(full_path)
    assert os.path.exists(f"{full_path}/thing.json")
    assert os.path.exists(f"{full_path}/what.txt")

    assert cacher.load()["message"] == "hello world!"


def test_raw_jupyter_notebook_cacher_saves_outputs(configured_test_manager):
    """The RawJuypterNotebookCacher should store both the cell content and
    the notebook file."""

    @cf.stage(outputs=["notebook"], cachers=[RawJupyterNotebookCacher])
    def write_notebook(record):
        cells = [
            ["print('hello world!')", "print('this is a test!')"],
            ["# this is another cell", "..."],
        ]
        return cells

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    write_notebook(r0)

    path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.params.hash}_write_notebook_notebook",
    )
    assert os.path.exists(f"{path}.ipynb")
    assert os.path.exists(f"{path}_cells.json")
    assert not os.path.exists(f"{path}.py")

    contents = JsonCacher(f"{path}.ipynb").load()
    assert len(contents["cells"]) == 2
    assert contents["cells"][0]["source"] == [
        "print('hello world!')\n",
        "print('this is a test!')",
    ]
    assert contents["cells"][1]["source"] == ["# this is another cell\n", "..."]


def test_extra_metadata_loaded_before_load(configured_test_manager):
    """Any extra metadata added in a cacher's save function should be available in the load function."""
    run_count = 0

    class UsesExtraMetadataCacher(Cacheable):
        def save(self, obj):
            self.extra_metadata["best_number"] = 13
            self.save_metadata()
            JsonCacher(self.get_path()).save(obj)

        def load(self):
            self.load_metadata()
            assert self.extra_metadata["best_number"] == 13
            return JsonCacher(self.get_path()).load()

    @cf.stage(outputs=["something"], cachers=[UsesExtraMetadataCacher])
    def do_thing(record):
        nonlocal run_count
        run_count += 1
        return "hello"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test2"))
    do_thing(r0)
    do_thing(r1)

    assert r0.state["something"] == "hello"
    assert r1.state["something"] == "hello"
    assert run_count == 1


def test_extra_metadata_used_inline(configured_test_manager):
    """Inline cacher should correctly handle extra_metadata as long as save_metadata() and
    load_metadata() are called correctly."""

    class UsesExtraMetadataCacher(Cacheable):
        def save(self, obj):
            self.extra_metadata["best_number"] = 13
            JsonCacher(self.get_path()).save(obj)
            self.save_metadata()

        def load(self):
            self.load_metadata()
            assert self.extra_metadata["best_number"] == 13
            return JsonCacher(self.get_path()).load()

    # r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    # UsesExtraMetadataCacher(f"{configured_test_manager.cache_path}/test_thing", record=r0).save("testing")
    UsesExtraMetadataCacher(f"{configured_test_manager.cache_path}/test_thing").save(
        "testing"
    )
    assert (
        UsesExtraMetadataCacher(
            f"{configured_test_manager.cache_path}/test_thing"
        ).load()
        == "testing"
    )
