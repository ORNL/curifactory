import curifactory as cf
from curifactory.caching import PickleCacher
from curifactory.reporting import JsonReporter
import json
import os
import pytest

from stages.cache_stages import filerefcacher_stage, filerefcacher_stage_multifile


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
        "r",
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
        "r",
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

    with open(list_path, "r") as infile:
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

    with open(list_path, "r") as infile:
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
    configured_test_manager
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


def test_aggregate_args_records_overwrite_doesnot_load_cache(configured_test_manager):
    """Calling an aggregate stage with valid args, twice, with other records with overwrite
    should NOT load from cache and execute.

    Running with the experiment CLI should ensure this doesn't happen (since --overwrite
    will apply to all args, it's set on an artifactmanager-level. However, edge cases with this
    in a notebook where the manager isn't set with overwrite could occur, and if any involved records
    require overwrite, we can assume an aggregate using them also needs to overwrite.
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

    assert call_count == 2


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
    configured_test_manager
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
