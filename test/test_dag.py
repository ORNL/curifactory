import curifactory as cf
from curifactory.dag import DAG


def test_child_records_empty_for_blank_records(configured_test_manager):
    """Records with no relation to eachother should have empty child_records"""
    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs("test1"))

    dag = DAG()
    dag.records.append(r0)
    dag.records.append(r1)

    assert len(dag.child_records(r0)) == 0
    assert len(dag.child_records(r1)) == 0


def test_child_records_after_make_copy(configured_test_manager):
    """A record that was copied should show the copied record as one of its children."""
    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))

    @cf.stage()
    def do_thing(record):
        t = 5 + 2
        print(t)

    r0 = do_thing(r0)
    r1 = r0.make_copy(cf.ExperimentArgs("test1"))

    dag = DAG()
    dag.records.append(r0)
    dag.records.append(r1)

    r0_children = dag.child_records(r0)
    assert len(r0_children) == 1
    assert len(dag.child_records(r1)) == 0
    assert r0_children[0] == r1
