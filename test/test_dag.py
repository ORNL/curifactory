import pytest

import curifactory as cf
from curifactory.caching import PickleCacher


def test_child_records_empty_for_blank_records(configured_test_manager):
    """Records with no relation to eachother should have empty child_records"""
    configured_test_manager.map_mode = True
    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters("test1"))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    r1 = dag.records[1]
    assert len(dag.child_records(r0)) == 0
    assert len(dag.child_records(r1)) == 0


def test_child_records_after_make_copy(configured_test_manager):
    """A record that was copied should show the copied record as one of its children."""
    configured_test_manager.map_mode = True

    @cf.stage()
    def do_thing(record):
        t = 5 + 2
        print(t)

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r0 = do_thing(r0)
    r1 = r0.make_copy(cf.ExperimentParameters("test1"))

    configured_test_manager.map_mode = False
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

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r0 = thing1(r0)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert not dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_when_record_copied_butunused(configured_test_manager):
    """is_output_used_anywhere should return false when there are no following stages in subsequent
    records that use it."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r0 = thing1(r0)

    r0.make_copy(cf.ExperimentParameters("test1"))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert not dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_in_aggregate_when_not_expected(configured_test_manager):
    """is_output_used_anywhere should return false when there is an aggregate using this record
    but does not list the variable as part of expected state."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.aggregate(outputs=["things"])
    def all_the_things(record, records):
        return "no"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r0 = thing1(r0)

    r1 = cf.Record(configured_test_manager, None)
    r1 = all_the_things(r1, [r0])

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert not dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_in_aggregate(configured_test_manager):
    """is_output_used_anywhere should return true when there is an aggregate using this record."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.aggregate(inputs=["thing"], outputs=["things"])
    def all_the_things(record, records, thing):
        return "no"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    r0 = thing1(r0)

    r1 = cf.Record(configured_test_manager, None)
    r1 = all_the_things(r1, [r0])

    configured_test_manager.map_mode = False
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

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    thing1(r0)
    thing2(r0)
    # thing2(thing1(r0))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert dag.is_output_used_anywhere(r0, 1, "thing")


def test_output_used_check_finds_output_in_later_input_of_copy(configured_test_manager):
    """An output that's used as an input in a later copy of a record should be found."""
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.stage(inputs=["thing"], outputs=["another_thing"])
    def thing2(record, thing):
        return "Sam I am"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    thing1(r0)
    r1 = r0.make_copy(cf.ExperimentParameters("test1"))
    thing2(r1)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert dag.is_output_used_anywhere(r0, 1, "thing")


def test_single_stage_is_leaf(configured_test_manager):
    """Make sure a single stage is in fact a leaf."""
    configured_test_manager.map_mode = True

    @cf.stage()
    def void_stares_back(record):
        print("If you stare into the abyss")

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    void_stares_back(r0)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert dag.is_leaf(r0, "void_stares_back")


def test_output_used_elsewhere_is_not_leaf(configured_test_manager):
    configured_test_manager.map_mode = True

    @cf.stage(outputs=["thing"])
    def thing1(record):
        return "green eggs and ham"

    @cf.stage(inputs=["thing"], outputs=["another_thing"])
    def thing2(record, thing):
        return "Sam I am"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test0"))
    thing2(thing1(r0))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    r0 = dag.records[0]
    assert not dag.is_leaf(r0, "thing1")
    assert dag.is_leaf(r0, "thing2")


@pytest.mark.parametrize(
    "outputs,kwargs,suppress_missing,expect_error",
    [
        (None, {}, False, True),
        (None, {"nothing": 1}, False, False),
        (None, {"nothing": 1}, True, False),
        (None, {}, True, False),
        # having an output shouldn't actually change the handling
        (["thing"], {}, False, True),
        (["thing"], {"nothing": 1}, False, False),
        (["thing"], {"nothing": 1}, True, False),
        (["thing"], {}, True, False),
    ],
)
def test_stage_with_missing_inputs_handled_correctly(
    configured_test_manager, outputs, kwargs, suppress_missing, expect_error
):
    """A stage requesting an input that doesn't exist in state should appropriately
    handle kwargs and suppress_missing passed to a stage in determining whether
    an error gets thrown or not."""
    configured_test_manager.map_mode = True

    @cf.stage(
        inputs=["nothing"], outputs=outputs, suppress_missing_inputs=suppress_missing
    )
    def do_nothing(record, nothing):
        return 6

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_nothing(r0, **kwargs)
    configured_test_manager.map_mode = False

    # TODO: check for error her
    if expect_error:
        with pytest.raises(KeyError):
            configured_test_manager.map_records()
            dag = configured_test_manager.map
            dag.determine_execution_list()
    else:
        configured_test_manager.map_records()
        dag = configured_test_manager.map
        dag.determine_execution_list()

        # expect to always execute a stage that has missing inputs
        assert dag.execution_list == [(0, "do_nothing")]


def test_single_record_execution_list_with_no_outputs(configured_test_manager):
    """A stage with no outputs should count as a leaf and should be in the execution list."""
    configured_test_manager.map_mode = True

    @cf.stage()
    def do_nothing(record):
        thing = 5 + 1
        thing += 1

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_nothing(r0)
    configured_test_manager.map_mode = False
    configured_test_manager.map_records()

    dag = configured_test_manager.map
    dag.determine_execution_list()
    assert dag.execution_list == [(0, "do_nothing")]


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        (False, [], [(0, "do_thing"), (0, "do_nothing")]),
        (True, [], [(0, "do_nothing")]),
        (False, ["do_thing"], [(0, "do_thing"), (0, "do_nothing")]),
        (True, ["do_thing"], [(0, "do_thing"), (0, "do_nothing")]),
        (False, ["do_thing", "do_nothing"], [(0, "do_thing"), (0, "do_nothing")]),
        (True, ["do_thing", "do_nothing"], [(0, "do_thing"), (0, "do_nothing")]),
        (True, ["do_nothing"], [(0, "do_nothing")]),
    ],
)
def test_single_record_execution_list_with_no_outputs_and_inputs(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """A stage with no outputs (but does have inputs) should count as a leaf and should
    be in the execution list."""
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing"])
    def do_thing(record):
        return 5

    @cf.stage(inputs=["thing"])
    def do_nothing(record, thing):
        thing = 5 + 1
        thing += 1

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_nothing(do_thing(r0))
    configured_test_manager.map_mode = False
    configured_test_manager.map_records()

    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached
    dag.determine_execution_list()
    assert dag.execution_list == expected_execution_list


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        (False, [], [(0, "thing1")]),
        (True, [], []),
        (False, ["thing1"], [(0, "thing1")]),
        (True, ["thing1"], [(0, "thing1")]),
    ],
)
def test_single_record_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for one stage in one record:

        (r0:thing1)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing1(r0)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached
    dag.determine_execution_list()

    assert dag.execution_list == expected_execution_list


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        # fmt: off
        ([False, False], [], [(0, "thing1"), (0, "thing2")]),
        ([True, False], [], [(0, "thing2")]),
        ([True, True], [], []),
        ([False, True], [], []),
        ([False, True], ["thing2"], [(0, "thing1"), (0, "thing2")]),
        ([True, False], ["thing2"], [(0, "thing2")]),
        ([True, True], ["thing2"], [(0, "thing2")]),
        ([True, True], ["thing1"], [(0, "thing1"), (0, "thing2")]),
        ([False, True], ["thing1"], [(0, "thing1"), (0, "thing2")]),
        ([False, False], ["thing1"], [(0, "thing1"), (0, "thing2")]),
        # fmt: on
    ],
)
def test_single_record_double_stage_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for two stages in one record:

        (r0:thing1)--(r0:thing2)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    @cf.stage(inputs=["thing1"], outputs=["thing2"])
    def thing2(record, thing1):
        return thing1 + 1

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing2(thing1(r0))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached[0]
    dag.artifacts[1].cached = cached[1]
    dag.determine_execution_list()

    assert len(dag.execution_list) == len(expected_execution_list)
    assert set(dag.execution_list) == set(expected_execution_list)


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        # fmt: off
        ([False, False, False], [], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([False, False, True], [], []),
        ([False, True, False], [], [(0, "thing3")]),
        ([True, False, False], [], [(0, "thing2"), (0, "thing3")]),
        ([True, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([True, False, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([True, False, True], ["thing2"], [(0, "thing2"), (0, "thing3")]),
        ([False, False, True], ["thing2"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        # fmt: on
    ],
)
def test_single_record_triple_stage_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for three stages in one record:

        (r0:thing1)--(r0:thing2)--(r0:thing3)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    @cf.stage(inputs=["thing1"], outputs=["thing2"])
    def thing2(record, thing1):
        return thing1 + 1

    @cf.stage(inputs=["thing2"], outputs=["thing3"])
    def thing3(record, thing2):
        return thing2 + 1

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing3(thing2(thing1(r0)))

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached[0]
    dag.artifacts[1].cached = cached[1]
    dag.artifacts[2].cached = cached[2]
    dag.determine_execution_list()

    assert len(dag.execution_list) == len(expected_execution_list)
    assert set(dag.execution_list) == set(expected_execution_list)


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        # fmt: off
        ([False, False, False], [], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([True, False, False], [], [(0, "thing2"), (0, "thing3")]),
        ([True, True, True], [], []),
        ([False, True, True], [], []),
        ([False, False, True], [], [(0, "thing1"), (0, "thing2")]),
        ([False, True, False], [], [(0, "thing1"), (0, "thing3")]),
        ([True, True, False], [], [(0, "thing3")]),
        ([True, False, True], [], [(0, "thing2")]),
        ([True, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([False, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([False, False, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (0, "thing3")]),
        ([True, True, True], ["thing2"], [(0, "thing2")]),
        ([True, True, True], ["thing3"], [(0, "thing3")]),
        ([False, True, True], ["thing2"], [(0, "thing1"), (0, "thing2")]),
        ([False, True, True], ["thing3"], [(0, "thing1"), (0, "thing3")]),
        # fmt: on
    ],
)
def test_single_record_triple_stage_nonsinglechain_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for three stages in one record, where two stages
    don't impact each other but both use the same outputs from the first stage

                    (r0:thing2)
                   /
        (r0:thing1)
                   \
                    (r0:thing3)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    @cf.stage(inputs=["thing1"], outputs=["thing2"])
    def thing2(record, thing1):
        return thing1 + 1

    @cf.stage(inputs=["thing1"], outputs=["thing3"])
    def thing3(record, thing1):
        return thing1 + 2

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing1(r0)
    thing2(r0)
    thing3(r0)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached[0]
    dag.artifacts[1].cached = cached[1]
    dag.artifacts[2].cached = cached[2]
    dag.determine_execution_list()

    assert len(dag.execution_list) == len(expected_execution_list)
    assert set(dag.execution_list) == set(expected_execution_list)


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        # fmt: off
        ([False, False, False], [], [(0, "thing1"), (0, "thing2"), (1, "thing3")]),
        ([True, False, False], [], [(0, "thing2"), (1, "thing3")]),
        ([True, True, True], [], []),
        ([False, True, True], [], []),
        ([False, False, True], [], [(0, "thing1"), (0, "thing2")]),
        ([False, True, False], [], [(0, "thing1"), (1, "thing3")]),
        ([True, True, False], [], [(1, "thing3")]),
        ([True, False, True], [], [(0, "thing2")]),
        ([True, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (1, "thing3")]),
        ([False, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (1, "thing3")]),
        ([False, False, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (1, "thing3")]),
        ([True, True, True], ["thing2"], [(0, "thing2")]),
        ([True, True, True], ["thing3"], [(1, "thing3")]),
        ([False, True, True], ["thing2"], [(0, "thing1"), (0, "thing2")]),
        ([False, True, True], ["thing3"], [(0, "thing1"), (1, "thing3")]),
        # fmt: on
    ],
)
def test_double_record_triple_stage_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for three stages in two records, where one
    record is a copy of the other after the first stage:

                    (r0:thing2)
                   /
        (r0:thing1)
                   \
                    (r1:thing3)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    @cf.stage(inputs=["thing1"], outputs=["thing2"])
    def thing2(record, thing1):
        return thing1 + 1

    @cf.stage(inputs=["thing1"], outputs=["thing3"])
    def thing3(record, thing1):
        return thing1 + 2

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing1(r0)
    r1 = r0.make_copy(cf.ExperimentParameters("test2"))
    thing2(r0)
    thing3(r1)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached[0]
    dag.artifacts[1].cached = cached[1]
    dag.artifacts[2].cached = cached[2]
    dag.determine_execution_list()

    assert len(dag.execution_list) == len(expected_execution_list)
    assert set(dag.execution_list) == set(expected_execution_list)


@pytest.mark.parametrize(
    "cached,overwrite_stages,expected_execution_list",
    [
        # fmt: off
        ([False, False, False, False], [], [(0, "thing1"), (0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([False, False, False, True], [], []),
        ([False, False, True, False], [], [(0, "thing1"), (0, "thing2"), (2, "agg_things")]),
        ([False, True, False, False], [], [(0, "thing1"), (1, "thing3"), (2, "agg_things")]),
        ([False, True, True, False], [], [(2, "agg_things")]),
        ([True, True, True, False], [], [(2, "agg_things")]),
        ([True, True, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([False, True, True, True], ["thing1"], [(0, "thing1"), (0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([True, True, False, True], ["thing2"], [(0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([True, False, True, True], ["thing3"], [(0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([True, True, True, True], ["thing2"], [(0, "thing2"), (2, "agg_things")]),
        ([True, True, True, True], ["thing3"], [(1, "thing3"), (2, "agg_things")]),
        ([False, False, False, True], ["thing2"], [(0, "thing1"), (0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([False, False, False, True], ["thing3"], [(0, "thing1"), (0, "thing2"), (1, "thing3"), (2, "agg_things")]),
        ([False, False, True, True], ["thing2"], [(0, "thing1"), (0, "thing2"), (2, "agg_things")]),
        ([False, True, False, True], ["thing3"], [(0, "thing1"), (1, "thing3"), (2, "agg_things")]),
        # fmt: on
    ],
)
def test_triple_record_quadruple_stage_execution_lists(
    configured_test_manager, cached, overwrite_stages, expected_execution_list
):
    """DAG-based execution determination should be correct for all possible
    cached/overwrite combinations for four stages in three records, where one
    record is a copy of the other after the first stage and the final stage
    aggregates the two former records:

                    (r0:thing2)
                   /           \
        (r0:thing1)             (r2:thing4)
                   \\           /
                    (r1:thing3)
    """
    configured_test_manager.map_mode = True
    configured_test_manager.overwrite_stages = overwrite_stages

    @cf.stage(outputs=["thing1"])
    def thing1(record):
        return 1

    @cf.stage(inputs=["thing1"], outputs=["thing"])
    def thing2(record, thing1):
        return thing1 + 1

    @cf.stage(inputs=["thing1"], outputs=["thing"])
    def thing3(record, thing1):
        return thing1 + 2

    @cf.aggregate(inputs=["thing"], outputs=["things"])
    def agg_things(record, records, thing):
        total = 0
        for r, value in thing.items():
            total += value
        return total

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    thing1(r0)
    r1 = r0.make_copy(cf.ExperimentParameters("test2"))
    thing2(r0)
    thing3(r1)
    r2 = cf.Record(configured_test_manager, None)
    agg_things(r2, [r0, r1])

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    dag.artifacts[0].cached = cached[0]
    dag.artifacts[1].cached = cached[1]
    dag.artifacts[2].cached = cached[2]
    dag.artifacts[3].cached = cached[3]
    dag.determine_execution_list()

    assert len(dag.execution_list) == len(expected_execution_list)
    assert set(dag.execution_list) == set(expected_execution_list)


# TODO: tests with two records two stages (single record first stage, two records run second stage)

# TODO: also tests where the outputs of a stage are each used as an input in a different stage


def test_dag_will_not_force_recompute_of_similar_stages(configured_test_manager):
    """A stage that is called multiple times with the same arguments and is not _initially_ cached
    should not be run more than once. (The fact that the DAG execution list doesn't update shouldn't
    preclude stage from determining a stage still doesn't actually need to run if it finds the right
    cached values.)"""

    run_count = 0

    @cf.stage(outputs=["thing"], cachers=[PickleCacher])
    def do_thing(record):
        nonlocal run_count
        run_count += 1
        return "hi"

    configured_test_manager.map_mode = True
    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(r0)
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(r1)

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert len(dag.execution_list) == 2
    assert run_count == 0

    actual_r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(actual_r0)
    actual_r1 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(actual_r1)

    assert run_count == 1


def test_dag_will_not_force_recompute_of_similar_aggregate_stages(
    configured_test_manager,
):
    """An agg stage that is called multiple times with the same arguments and is not _initially_ cached
    should not be run more than once. (The fact that the DAG execution list doesn't update shouldn't
    preclude stage from determining a stage still doesn't actually need to run if it finds the right
    cached values.)"""

    run_count = 0

    @cf.aggregate(outputs=["thing"], cachers=[PickleCacher])
    def do_thing(record, records):
        nonlocal run_count
        run_count += 1
        return "hi"

    configured_test_manager.map_mode = True
    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(r0, [])
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(r1, [])

    configured_test_manager.map_mode = False
    configured_test_manager.map_records()
    dag = configured_test_manager.map

    assert len(dag.execution_list) == 2
    assert run_count == 0

    actual_r0 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(actual_r0, [])
    actual_r1 = cf.Record(configured_test_manager, cf.ExperimentParameters("test"))
    do_thing(actual_r1, [])

    assert run_count == 1
