import os
from dataclasses import dataclass
from enum import IntEnum

import curifactory as cf
from curifactory import reporting
from curifactory.caching import JsonCacher
from curifactory.reporting import JsonReporter


def test_reportables_cached(configured_test_manager):
    """Re-running a stage with cached outputs and reportables should still reload the old reportables."""

    @cf.stage(None, ["stuff"], [JsonCacher])
    def stage_with_reportables(record):
        dictionary = {"thing1": "testing"}
        record.report(JsonReporter(dictionary))

        with open(os.path.join(record.manager.cache_path, "stage_ran"), "w") as outfile:
            outfile.write("\n")

        return dictionary

    ran_path = os.path.join(configured_test_manager.cache_path, "stage_ran")

    r0 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    stage_with_reportables(r0)

    assert len(configured_test_manager.reportables) == 1
    assert os.path.exists(ran_path)
    os.remove(ran_path)

    r1 = cf.Record(configured_test_manager, cf.ExperimentArgs(name="test"))
    stage_with_reportables(r1)

    assert len(configured_test_manager.reportables) == 2
    assert not os.path.exists(ran_path)


def test_no_angle_brackets_in_report_argset_dump(configured_test_manager):
    """The output pre tag in the report argset dump should not contain un-escaped angle brackets."""

    class MyEnum(IntEnum):
        thing1 = 0
        thing2 = 2

    @dataclass
    class MyArgs(cf.ExperimentArgs):
        thing: MyEnum = MyEnum.thing1

    cf.Record(configured_test_manager, MyArgs())
    lines = reporting.render_report_argset_dump(configured_test_manager)
    all_text = "".join(lines[2:-1])
    assert "<" not in all_text
    assert ">" not in all_text
