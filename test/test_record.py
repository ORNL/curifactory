"""Testing record functionality."""

import json
import os

from pytest_mock import mocker  # noqa: F401 -- flake8 doesn't see it's used as fixture

from curifactory import ExperimentArgs, Record, aggregate, hashing, stage


def test_record_sets_hash(configured_test_manager):
    """A record that is passed an argset should appropriately set the hash on it immediately."""
    record = Record(configured_test_manager, ExperimentArgs(name="testing"))
    assert record.args.hash is not None


def test_record_doesnot_set_hash_for_none_args(configured_test_manager):
    """A record that is passed an argset should appropriately set the hash on it immediately."""
    record = Record(configured_test_manager, None)
    assert record.args is None


def test_record_stores_hash_when_not_dry(configured_test_manager):
    """A record that is passed an argset with a non-dry-mode manager should store the args in the
    param_registry.json."""
    record = Record(  # noqa: F841
        configured_test_manager, ExperimentArgs(name="testing")
    )

    reg_path = os.path.join(
        configured_test_manager.manager_cache_path, "params_registry.json"
    )
    with open(reg_path) as infile:
        reg = json.load(infile)

    keys = list(reg.keys())
    assert len(keys) == 1
    assert reg[keys[0]]["name"] == "testing"


def test_record_doesnot_store_hash_when_dry(configured_test_manager):
    """A record that is passed an argset with a dry-mode manager should not store the args in
    the param_registry.json."""
    configured_test_manager.dry = True
    record = Record(  # noqa: F841
        configured_test_manager, ExperimentArgs(name="testing")
    )

    reg_path = os.path.join(
        configured_test_manager.manager_cache_path, "params_registry.json"
    )
    assert not os.path.exists(reg_path)


def test_record_doesnot_store_hash_when_parallelmode(configured_test_manager):
    """A record that is passed an argset with a parallel-mode manager should not store the
    args in the param_registry.json."""
    configured_test_manager.parallel_mode = True
    record = Record(  # noqa: F841
        configured_test_manager, ExperimentArgs(name="testing")
    )

    reg_path = os.path.join(
        configured_test_manager.manager_cache_path, "params_registry.json"
    )
    assert not os.path.exists(reg_path)


def test_record_doesnot_store_combo_hash_when_parallel_mode(configured_test_manager):
    """In a parallel-mode run, the record should not store the combo hash of an
    aggregate stage in the param_registry.json."""
    configured_test_manager.parallel_mode = True

    @aggregate(["testing"])
    def agg_stage(record, records):
        return "test"

    r0 = Record(configured_test_manager, None)
    r1 = Record(configured_test_manager, ExperimentArgs(name="test"))
    r0 = agg_stage(r0, [r1])

    reg_path = os.path.join(
        configured_test_manager.manager_cache_path, "params_registry.json"
    )
    assert not os.path.exists(reg_path)


# TODO: test_record_gets_combo_hash_for_aggregate (check that is_aggregate sets)
def test_record_gets_combo_hash_for_aggregate(configured_test_manager):
    @aggregate(["testing"])
    def agg_stage(record, records):
        return "test"

    r0 = Record(configured_test_manager, None)
    r1 = Record(configured_test_manager, ExperimentArgs(name="test"))
    r0 = agg_stage(r0, [r1])
    combo_hash = hashing.add_args_combo_hash(
        r0, [r1], "", False
    )  # TODO: what about when None passed in? Empty array?

    assert r0.is_aggregate
    assert r0.combo_hash == combo_hash


# TODO: test_record_with_aggregate_doesnot_change_args_hash (do a normal stage with those args and an agg stage with those args)


def test_record_make_copy_retains_state(configured_test_manager):
    """When a record is copied, the resulting record should have the same values in state
    as the source record."""

    @stage([], outputs=["test"])
    def output_stage(record):
        return "hello world"

    r0 = Record(
        configured_test_manager, ExperimentArgs(name="test1")
    )  # TODO: include args
    r0 = output_stage(r0)

    r1 = r0.make_copy(ExperimentArgs(name="test2"))
    assert "test" in r1.state
    assert r1.state["test"] == "hello world"
    assert r1.args.name == "test2"


def test_record_make_copy_adds_record_to_manager(configured_test_manager):
    """Making a record copy with default values should add one (and only one) record
    to the manager."""

    @stage([], outputs=["test"])
    def output_stage(record):
        return "hello world"

    r0 = Record(configured_test_manager, ExperimentArgs(name="test0"))
    r0 = output_stage(r0)
    assert len(configured_test_manager.records) == 1

    r0.make_copy(ExperimentArgs(name="test1"))
    assert len(configured_test_manager.records) == 2


def test_record_make_copy_doesnot_add_record_to_manager_when_specified(
    configured_test_manager,
):
    """Making a record copy with default values should add one (and only one) record
    to the manager."""

    @stage([], outputs=["test"])
    def output_stage(record):
        return "hello world"

    r0 = Record(configured_test_manager, ExperimentArgs(name="test0"))
    r0 = output_stage(r0)
    assert len(configured_test_manager.records) == 1

    r0.make_copy(ExperimentArgs(name="test1"), add_to_manager=False)
    assert len(configured_test_manager.records) == 1
