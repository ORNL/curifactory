import curifactory as cf


def test_child_records_empty_for_blank_records(configured_test_manager):
    """Records with no relation to eachother should have empty child_records"""
    configured_test_manager.map_mode = True
    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs("test1"))

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert len(dag.child_records(r0)) == 0
    assert len(dag.child_records(r1)) == 0


def test_child_records_after_make_copy(configured_test_manager):
    """A record that was copied should show the copied record as one of its children."""
    configured_test_manager.map_mode = True

    @cf.stage()
    def do_thing(record):
        t = 5 + 2
        print(t)

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r0 = do_thing(r0)
    r1 = r0.make_copy(cf.ExperimentArgs("test1"))

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    r1 = dag.records[1]
    r0_children = dag.child_records(r0)
    assert len(r0_children) == 1
    assert len(dag.child_records(r1)) == 0
    assert r0_children[0] == r1


def test_output_used_check_when_no_following_stages(configured_test_manager):
    """is_output_used_anywhere should return false when there are no following stages or
    records."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r0 = thing1(r0)

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert not dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_when_record_copied_butunused(configured_test_manager):
    """is_output_used_anywhere should return false when there are no following stages in subsequent
    records that use it."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r0 = thing1(r0)

    r0.make_copy(cf.ExperimentArgs("test1"))

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert not dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_in_aggregate(configured_test_manager):
    """is_output_used_anywhere should return true when there is an aggregate using this record."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.aggregate(outputs=["things"])
    def all_the_things(record, records):
        return "no"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    r0 = thing1(r0)

    r1 = cf.Record(configured_test_manager, None)
    r1 = all_the_things(r1, [r0])

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_finds_output_in_later_input(configured_test_manager):
    """An output that's actually used later should be found."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.stage(inputs=["thing"], outputs=["another_thing"])
    def thing2(record, thing):
        return "Sam I am"

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test0"))
    thing2(thing1(r0))

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert dag.is_output_used_anywhere(r0, 1, "thing")


def test_single_stage_is_leaf(configured_test_manager):
    """Make sure a single stage is in fact a leaf."""
    configured_test_manager.map_mode = True

    @cf.stage()
    def void_stares_back(record):
        print("If you stare into the abyss")

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs("test"))
    void_stares_back(r0)

    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert dag.is_leaf(r0, "void_stares_back")
