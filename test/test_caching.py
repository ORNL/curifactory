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
    """Running an aggregate stage with a reportable should cache the reportable and a list of reportable cache files."""

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
        f"test_{r0.args.hash}_basic_agg_reportable_reportables_file_list.json",
    )

    reportable_path = os.path.join(
        configured_test_manager.cache_path,
        f"test_{r0.args.hash}_basic_agg_reportable_reportables/(Aggregate)_test_basic_agg_reportable_0.pkl",
    )

    print([thing for thing in os.listdir(configured_test_manager.cache_path)])
    print("---")
    print(list_path)
    print(reportable_path)

    assert os.path.exists(list_path)

    with open(list_path, "r") as infile:
        paths = json.load(infile)

    assert len(paths) == 1
    assert paths[0] == reportable_path
    assert os.path.exists(reportable_path)


# def test_reportables_are_cached_with_store_full(configured_test_manager):
#     pass
