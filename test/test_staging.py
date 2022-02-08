import pytest
from curifactory import (
    stage,
    aggregate,
    Record,
    InputSignatureError,
    OutputSignatureError,
    EmptyCachersError,
    CachersMismatchError,
)
from curifactory.caching import PickleCacher, Lazy


# --------------------------
# @stage tests
# --------------------------


def test_stores_output_in_record(configured_test_manager):
    """Returned output from stage function should exist in record state."""

    @stage([], ["tester"])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    output_stage(record)
    assert record.state["tester"] == "hello world"


def test_stage_outputs_none(configured_test_manager):
    """Stage outputs set to None should be equivalent to [] and should not crash."""

    @stage([], outputs=None)
    def output_stage(record):
        x = 5
        del x

    record = Record(configured_test_manager, None)
    output_stage(record)


def test_stage_inputs_none(configured_test_manager):
    """Stage inputs set to None should be equivalent to [] and should not crash."""

    @stage(inputs=None, outputs=["tester"])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    output_stage(record)
    assert record.state["tester"] == "hello world"


def test_stores_multiple_outputs_in_record(configured_test_manager):
    """Multiple returned outputs from stage function should exist in record state."""

    @stage([], ["test1", "test2"])
    def output_stage(record):
        return "hello world", 13

    record = Record(configured_test_manager, None)
    output_stage(record)
    assert record.state["test1"] == "hello world"
    assert record.state["test2"] == 13


def test_returns_less_than_expected_errors(configured_test_manager):
    """A function that doesn't return the same number of objects as specified in the stage outputs should throw an OutputSignatureError."""

    @stage([], ["test1", "test2"])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        output_stage(record)


def test_empty_cachers_array_errors(configured_test_manager):
    """Don't let the user write [] for cachers list, as it always shortcircuits."""
    # NOTE: technically this could probably just be a special case handled by staging.py, but I think specifying [] for cachers is kind of unclear anyway.
    @stage([], [], [])
    def stage_that_does_nothing(record):
        i_am_very_important = 5 + 3
        del i_am_very_important

    record = Record(configured_test_manager, None)
    with pytest.raises(EmptyCachersError):
        stage_that_does_nothing(record)


def test_cachers_count_mismatch_errors(configured_test_manager):
    """Specifying a different number of cachers than output args should throw a CachersMismatchError."""

    @stage([], ["thing1", "thing2"], [PickleCacher])
    def bad_caching_vibes(record):
        return 1, 2

    record = Record(configured_test_manager, None)
    with pytest.raises(CachersMismatchError):
        bad_caching_vibes(record)


def test_cachers_correct_count(configured_test_manager):
    """Specifying the correct number of cachers for outputs works fine."""

    @stage([], ["thing1", "thing2"], [PickleCacher] * 2)
    def good_caching_vibes(record):
        return 1, 2

    record = Record(configured_test_manager, None)
    good_caching_vibes(record)
    # NOTE: will test caches correctly in caching tests


def test_return_tuple_for_one_output_errors(configured_test_manager):
    """Returning something that is a tuple does not work for a single specified output, this should throw an OutputSignatureError."""

    @stage([], ["my_output"])
    def return_tuple(record):
        multiple_values = (1, 2)
        return multiple_values

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        return_tuple(record)


def test_return_tuplefied_tuple_for_one_output(configured_test_manager):
    """Returning something that is a tuple as a single output value should be tuplefied again."""

    @stage([], ["my_output"])
    def return_tuple(record):
        multiple_values = (1, 2)
        return (multiple_values,)

    record = Record(configured_test_manager, None)
    return_tuple(record)
    assert record.state["my_output"] == (1, 2)


def test_return_array_for_one_output(configured_test_manager):
    """Returning an array as a single output should not have the same issues as a tuple, and should work fine."""

    @stage([], ["my_output"])
    def return_array(record):
        multiple_values = [1, 2]
        return multiple_values

    record = Record(configured_test_manager, None)
    return_array(record)
    assert record.state["my_output"] == [1, 2]


def test_takes_input_from_record(configured_test_manager):
    """A specified input in the stage should pass in that value from the pre-existing record state."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    record.state["my_input"] = 13
    replicate_input(record)
    assert record.state["replicated_input"] == 13


def test_mssing_input_errors(configured_test_manager):
    """A stage input that is not found in the record's state should throw a KeyError."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    with pytest.raises(KeyError):
        replicate_input(record)


def test_missing_input_with_suppress_and_no_default_errors(configured_test_manager):
    """If suppress_missing_inputs is set on the stage but no defaults were specified for the missing ones, we should get an InputSignatureError."""

    @stage(["my_input"], ["replicated_input"], suppress_missing_inputs=True)
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    with pytest.raises(InputSignatureError):
        replicate_input(record)


def test_input_overwritten_by_kwarg(configured_test_manager):
    """A directly passed input argument on the stage function should override whatever was in the record's state previously."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    record.state["my_input"] = 13
    replicate_input(record, my_input=15)
    assert record.state["replicated_input"] == 15


def test_missing_input_but_default_without_suppress_errors(configured_test_manager):
    """Even if there's a default value for an input argument, if suppress isn't specified and we don't pass a value in on the stage call, we should get an error."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_input=15):
        return my_input

    record = Record(configured_test_manager, None)
    with pytest.raises(KeyError):
        replicate_input(record)


def test_missing_input_but_default_with_suppress(configured_test_manager):
    """If a stage has suppressed missing values and we don't pass the missing one in on the stage call, allow the default value to go through without error."""

    @stage(["my_input"], ["replicated_input"], suppress_missing_inputs=True)
    def replicate_input(record, my_input=15):
        return my_input

    record = Record(configured_test_manager, None)
    replicate_input(record)
    assert record.state["replicated_input"] == 15


def test_missing_input_but_kwarg_passed_with_suppress(configured_test_manager):
    """If we specify an input value directly in the stage call, allow it to go through even if it's missing from the record."""

    @stage(["my_input"], ["replicated_input"], suppress_missing_inputs=True)
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    replicate_input(record, my_input=15)
    assert record.state["replicated_input"] == 15


def test_missing_input_but_kwarg_passed_without_suppress(configured_test_manager):
    """If we specify an input value directly in the stage call, allow it to go through even if it's missing from the record and we don't have suppress enabled."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_input):
        return my_input

    record = Record(configured_test_manager, None)
    replicate_input(record, my_input=15)
    assert record.state["replicated_input"] == 15


def test_input_name_incorrect(configured_test_manager):
    """Stage input string names that do not match the function signature variable names should throw an InputSignatureError."""

    @stage(["my_input"], ["replicated_input"])
    def replicate_input(record, my_wrong_input):
        return my_wrong_input

    record = Record(configured_test_manager, None)
    record.state["my_input"] = 13
    with pytest.raises(InputSignatureError):
        replicate_input(record)


def test_lazy_obj_in_record(configured_test_manager):
    """Ensure a lazy object is put into state from a lazy output stage, and ensure that it reloads correctly when used."""

    @stage([], [Lazy("tester")], cachers=[PickleCacher])
    def output_stage(record):
        return "hello world"

    @stage(["tester"], outputs=["output"])
    def use_lazy(record, tester):
        return tester

    record = Record(configured_test_manager, None)
    output_stage(record)
    record.state.resolve = False
    assert type(record.state["tester"]) == Lazy
    record.state.resolve = True

    use_lazy(record)
    assert record.state["output"] == "hello world"


def test_lazy_disabled_on_ignore_lazy(configured_test_manager):
    """Lazy objects should be replaced with str counterparts if ignore_lazy is set on the manager."""

    @stage([], [Lazy("tester")], cachers=[PickleCacher])
    def output_stage(record):
        return "hello world"

    configured_test_manager.ignore_lazy = True
    record = Record(configured_test_manager, None)
    output_stage(record)
    assert type(record.state["tester"]) == str
    record.state.resolve = False
    assert record.state["tester"] == "hello world"


def test_lazy_forced_on_manager_lazy(configured_test_manager):
    """All objects should be lazy if lazy is set on the manager."""

    @stage([], ["tester"], cachers=[PickleCacher])
    def output_stage(record):

        return "hello world"

    configured_test_manager.lazy = True
    record = Record(configured_test_manager, None)
    output_stage(record)
    record.state.resolve = False
    assert type(record.state["tester"]) == Lazy
    record.state.resolve = True
    assert record.state["tester"] == "hello world"


def test_error_on_missing_lazy_cacher(configured_test_manager):
    """If no cacher is given for a lazy object, an error should be thrown."""

    @stage([], [Lazy("tester")])
    def output_stage(record):
        return "hello world"

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        output_stage(record)
    # record.state.resolve = False
    # assert type(record.state["tester"]) == Lazy
    # assert type(record.state["tester"].cacher) == PickleCacher


def test_cacher_injected_on_manager_lazy(configured_test_manager):
    """If lazy is set on the manager and an object has no cacher, inject a PickleCacher."""

    @stage([], ["tester"])
    def output_stage(record):
        return "hello world"

    configured_test_manager.lazy = True
    record = Record(configured_test_manager, None)
    output_stage(record)
    record.state.resolve = False
    assert type(record.state["tester"]) == Lazy
    assert type(record.state["tester"].cacher) == PickleCacher


def test_cacher_not_injected_on_manager_ignore_lazy(configured_test_manager):
    """If ignore_lazy is set on the manager and a Lazy object has no cacher, do not error."""
    # NOTE: in theory this behavior is so that if someone gives you buggy stages, you can "fix" the stage without having to actually go in and modify the cachers.

    @stage([], [Lazy("tester")])
    def output_stage(record):
        return "hello world"

    configured_test_manager.ignore_lazy = True
    record = Record(configured_test_manager, None)
    output_stage(record)
    record.state.resolve = False
    assert type(record.state["tester"]) == str
    assert record.state["tester"] == "hello world"


# --------------------------
# @aggregate tests
# --------------------------


def test_aggregate_stores_output_in_record(configured_test_manager):
    """An aggregate output should exist in the record state."""

    @aggregate(["output"])
    def small_aggregate(record, records):
        return "hello world"

    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])  # TODO: blank records array crashes??
    assert record.state["output"] == "hello world"


def test_aggregate_stores_multiple_outputs_in_record(configured_test_manager):
    """Multiple returned outputs from the stage should exist in the record state."""

    @aggregate(["thing1", "thing2"])
    def small_aggregate(record, records):
        return "hello world", 13

    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])
    assert record.state["thing1"] == "hello world"
    assert record.state["thing2"] == 13


def test_aggregate_returns_less_than_expected_errors(configured_test_manager):
    """A function that doesn't return the same number of objects as specified in the aggregate outputs should throw an OutputSignatureError."""

    @aggregate(["test1", "test2"])
    def output_stage(record, records):
        return "hello world"

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        output_stage(record, [record])


def test_aggregate_empty_cachers_array_errors(configured_test_manager):
    """Don't let the user write [] for cachers list, as it always shortcircuits."""
    # NOTE: technically this could probably just be a special case handled by staging.py, but I think specifying [] for cachers is kind of unclear anyway.
    @aggregate([], [])
    def aggregate_stage_that_does_nothing(record, records):
        i_am_very_important = 5 + 3
        del i_am_very_important

    record = Record(configured_test_manager, None)
    with pytest.raises(EmptyCachersError):
        aggregate_stage_that_does_nothing(record, [record])


def test_aggregate_cachers_count_mismatch_errors(configured_test_manager):
    """Specifying a different number of cachers than output args should throw a CachersMismatchError."""

    @aggregate(["thing1", "thing2"], [PickleCacher])
    def bad_caching_vibes(record, records):
        return 1, 2

    record = Record(configured_test_manager, None)
    with pytest.raises(CachersMismatchError):
        bad_caching_vibes(record, [record])


def test_aggregate_cachers_correct_count(configured_test_manager):
    """Specifying the correct number of cachers for outputs works fine."""

    @aggregate(["thing1", "thing2"], [PickleCacher] * 2)
    def good_caching_vibes(record, records):
        return 1, 2

    record = Record(configured_test_manager, None)
    good_caching_vibes(record, [record])
    # NOTE: will test caches correctly in caching tests


def test_aggregate_return_tuple_for_one_output_errors(configured_test_manager):
    """Returning something that is a tuple does not work for a single specified output, this should throw an OutputSignatureError."""

    @aggregate(["my_output"])
    def return_tuple(record, records):
        multiple_values = (1, 2)
        return multiple_values

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        return_tuple(record, [record])


def test_aggregate_return_tuplefied_tuple_for_one_output(configured_test_manager):
    """Returning something that is a tuple as a single output value should be tuplefied again."""

    @aggregate(["my_output"])
    def return_tuple(record, records):
        multiple_values = (1, 2)
        return (multiple_values,)

    record = Record(configured_test_manager, None)
    return_tuple(record, [record])
    assert record.state["my_output"] == (1, 2)


def test_aggregate_return_array_for_one_output(configured_test_manager):
    """Returning an array as a single output should not have the same issues as a tuple, and should work fine."""

    @aggregate(["my_output"])
    def return_array(record, records):
        multiple_values = [1, 2]
        return multiple_values

    record = Record(configured_test_manager, None)
    return_array(record, [record])
    assert record.state["my_output"] == [1, 2]


def test_aggregate_gets_records_states(configured_test_manager):
    """Inside the aggregate, we should be able to get values from the states of the manually passed in records."""

    @aggregate(["output"])
    def small_aggregate(record, records):
        total = 0
        for r in records:
            total += r.state["input"]
        return total

    record1 = Record(configured_test_manager, None)
    record2 = Record(configured_test_manager, None)
    record3 = Record(configured_test_manager, None)

    record1.state["input"] = 3
    record2.state["input"] = 2
    small_aggregate(record3, [record1, record2])
    assert record3.state["output"] == 5


def test_aggregate_gets_no_manager_records(configured_test_manager):
    """Calling an aggregate stage without records and with no records on the manager should not crash."""

    @aggregate(["output"])
    def small_aggregate(record, records):
        total = 0
        for r in records:
            total += r.state["input"]
        return total

    record = Record(configured_test_manager, None, hide=True)
    small_aggregate(record)
    assert record.state["output"] == 0


def test_aggregate_gets_manager_records_states(configured_test_manager):
    """Inside the aggregate, we should be passed all records on the manager by default, if no records explicitly passed."""

    @aggregate(["output"])
    def small_aggregate(record, records):
        total = 0
        for r in records:
            total += r.state["input"]
        return total

    record1 = Record(configured_test_manager, None)
    record2 = Record(configured_test_manager, None)
    record3 = Record(configured_test_manager, None, hide=True)

    record1.state["input"] = 3
    record2.state["input"] = 2

    small_aggregate(record3)
    assert record3.state["output"] == 5


def test_aggregate_lazy_obj_in_record(configured_test_manager):
    """Ensure a lazy object is put into state from a lazy output aggregate stage, and ensure that it reloads correctly when used."""

    @aggregate([Lazy("output")], cachers=[PickleCacher])
    def small_aggregate(record, records):
        total = 0
        for r in records:
            total += r.state["input"]
        return total

    @stage(["output"], outputs=["actual_output"])
    def use_lazy(record, output):
        return output

    record1 = Record(configured_test_manager, None)
    record2 = Record(configured_test_manager, None)
    record3 = Record(configured_test_manager, None, hide=True)

    record1.state["input"] = 3
    record2.state["input"] = 2

    small_aggregate(record3)
    record3.state.resolve = False
    assert type(record3.state["output"]) == Lazy
    record3.state.resolve = True

    use_lazy(record3)
    assert record3.state["actual_output"] == 5


def test_aggregate_lazy_disabled_on_ignore_lazy(configured_test_manager):
    """Lazy objects should be replaced with str counterparts if ignore_lazy is set on the manager."""

    @aggregate([Lazy("output")], cachers=[PickleCacher])
    def small_aggregate(record, records):
        return "hello world"

    configured_test_manager.ignore_lazy = True
    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])
    record.state.resolve = False
    assert type(record.state["output"]) == str
    assert record.state["output"] == "hello world"


def test_aggregate_lazy_forced_on_manager_lazy(configured_test_manager):
    """All objects should be lazy if lazy is set on the manager."""

    @aggregate(["output"], cachers=[PickleCacher])
    def small_aggregate(record, records):
        return "hello world"

    configured_test_manager.lazy = True
    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])
    record.state.resolve = False
    assert type(record.state["output"]) == Lazy
    record.state.resolve = True
    assert record.state["output"] == "hello world"


def test_aggregate_error_on_missing_lazy_cacher(configured_test_manager):
    """If no cacher is given for a lazy object, an error should be thrown."""

    @aggregate([Lazy("output")])
    def small_aggregate(record, records):
        return "hello world"

    record = Record(configured_test_manager, None)
    with pytest.raises(OutputSignatureError):
        small_aggregate(record, [record])


def test_aggregate_cacher_injected_on_manager_lazy(configured_test_manager):
    """If lazy is set on the manager and an object has no cacher, inject a PickleCacher."""

    @aggregate(["output"])
    def small_aggregate(record, records):
        return "hello world"

    configured_test_manager.lazy = True
    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])
    record.state.resolve = False
    assert type(record.state["output"]) == Lazy
    assert type(record.state["output"].cacher) == PickleCacher


def test_aggregate_cacher_not_injected_on_manager_ignore_lazy(configured_test_manager):
    """If ignore_lazy is set on the manager and a Lazy object has no cacher, do not error."""
    # NOTE: in theory this behavior is so that if someone gives you buggy stages, you can "fix" the stage without having to actually go in and modify the cachers.

    @aggregate([Lazy("output")])
    def small_aggregate(record, records):
        return "hello world"

    configured_test_manager.ignore_lazy = True
    record = Record(configured_test_manager, None)
    small_aggregate(record, [record])
    record.state.resolve = False
    assert type(record.state["output"]) == str
    assert record.state["output"] == "hello world"


def test_aggregate_auto_resolve_lazy_state(configured_test_manager):
    """A lazy cached object in state should auto-resolve when we access it in an aggregate."""

    @stage([], [Lazy("tester")], cachers=[PickleCacher])
    def output_stage(record):
        return "hello world"

    @aggregate(["reproduced_output"])
    def small_aggregate(record, records):
        return records[0].state["tester"]

    record1 = Record(configured_test_manager, None)
    record2 = Record(configured_test_manager, None, hide=True)

    output_stage(record1)
    record1.state.resolve = False
    assert type(record1.state["tester"]) == Lazy
    record1.state.resolve = True

    small_aggregate(record2, [record1])
    assert record2.state["reproduced_output"] == "hello world"
