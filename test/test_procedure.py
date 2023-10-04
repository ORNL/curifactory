import pytest

from curifactory import ExperimentParameters, Procedure, aggregate, stage
from curifactory.procedure import NoArtifactManagerError


@stage(outputs=["thing1"])
def do_thing_1(record):
    return 5


@stage(["thing1"], ["thing2"])
def do_thing_2(record, thing1):
    return thing1 + 6


@aggregate(["thing2"], ["total"])
def combine(record, records, thing2):
    total = 0
    for thing in thing2.values():
        total += thing
    return total


def test_procedure_with_manager_at_init(configured_test_manager):
    """A procedure created with a manager should run with that manager."""

    proc = Procedure([do_thing_1, do_thing_2], configured_test_manager)

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")

    r1 = proc.run(p1)
    r2 = proc.run(p2)

    assert len(configured_test_manager.records) == 2
    assert r1.params.name == "params1"
    assert r2.params.name == "params2"
    assert configured_test_manager.records[0].params.name == "params1"
    assert configured_test_manager.records[1].params.name == "params2"


def test_procedure_without_manager_at_init_but_at_run(configured_test_manager):
    """A procedure created without a manager, and then with one specified at run, should
    run with that manager."""

    proc = Procedure([do_thing_1, do_thing_2])

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")

    r1 = proc.run(p1, manager=configured_test_manager)
    r2 = proc.run(p2, manager=configured_test_manager)

    assert len(configured_test_manager.records) == 2
    assert r1.params.name == "params1"
    assert r2.params.name == "params2"
    assert configured_test_manager.records[0].params.name == "params1"
    assert configured_test_manager.records[1].params.name == "params2"


def test_procedure_without_manager_at_init_or_run_fails(configured_test_manager):
    """A procedure created without a manager, and then does not specify one at run should
    throw an exception."""

    proc = Procedure([do_thing_1, do_thing_2])

    p1 = ExperimentParameters(name="params1")

    with pytest.raises(NoArtifactManagerError):
        proc.run(p1)


def test_procedure_beginning_with_aggregate_from_prior_proc_works(
    configured_test_manager,
):
    """A procedure that starts with an aggregate and specifies a previous procedure should
    correctly use the records from that procedure."""

    proc1 = Procedure([do_thing_1, do_thing_2], configured_test_manager)
    proc2 = Procedure([combine], configured_test_manager, previous_proc=proc1)

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")

    proc1.run(p1)
    r2 = proc2.run(None)

    assert r2.state["total"] == 11

    proc1.run(p2)
    r3 = proc2.run(None)

    assert r3.state["total"] == 22


def test_procedure_beginning_with_aggregate_from_prior_proc_works_wo_manager_init(
    configured_test_manager,
):
    """A procedure that starts with an aggregate and specifies a previous procedure should
    correctly use the records from that procedure, even when manager specified at .run().
    """

    proc1 = Procedure([do_thing_1, do_thing_2])
    proc2 = Procedure([combine], previous_proc=proc1)

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")

    proc1.run(p1, manager=configured_test_manager)
    r2 = proc2.run(None, manager=configured_test_manager)

    assert r2.state["total"] == 11

    proc1.run(p2, manager=configured_test_manager)
    r3 = proc2.run(None, manager=configured_test_manager)

    assert r3.state["total"] == 22


def test_procedure_aggregate_with_specified_records(configured_test_manager):
    """A procedure that starts with an aggregate and specifies the records to use should
    correctly use those records."""

    proc1 = Procedure([do_thing_1, do_thing_2], configured_test_manager)
    proc2 = Procedure([combine], configured_test_manager)

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")

    r1 = proc1.run(p1)
    r2 = proc1.run(p2)
    r3 = proc2.run(None, records=[r1, r2])

    assert r3.state["total"] == 22


def test_procedure_when_no_records_specified_grabs_all_from_manager(
    configured_test_manager,
):
    """A procedure starting with an aggregate should grab all current records on the manager if
    none were provided."""

    proc1 = Procedure([do_thing_1, do_thing_2], configured_test_manager)
    proc2 = Procedure([combine], configured_test_manager)

    p1 = ExperimentParameters(name="params1")
    p2 = ExperimentParameters(name="params2")
    p3 = ExperimentParameters(name="params3")

    proc1.run(p1)
    proc1.run(p2)
    proc1.run(p3)

    r1 = proc2.run(None)

    assert r1.state["total"] == 33
