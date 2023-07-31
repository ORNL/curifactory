import os
from dataclasses import dataclass
from enum import IntEnum

from graphviz import Digraph

import curifactory as cf
from curifactory import reporting
from curifactory.caching import JsonCacher, PickleCacher
from curifactory.reporting import JsonReporter, _add_record_subgraph, render_reportable


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

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    stage_with_reportables(r0)

    assert len(configured_test_manager.reportables) == 1
    assert os.path.exists(ran_path)
    os.remove(ran_path)

    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    stage_with_reportables(r1)

    assert len(configured_test_manager.reportables) == 2
    assert not os.path.exists(ran_path)


def test_no_angle_brackets_in_report_argset_dump(configured_test_manager):
    """The output pre tag in the report argset dump should not contain un-escaped angle brackets."""

    class MyEnum(IntEnum):
        thing1 = 0
        thing2 = 2

    @dataclass
    class MyArgs(cf.ExperimentParameters):
        thing: MyEnum = MyEnum.thing1

    cf.Record(configured_test_manager, MyArgs())
    lines = reporting.render_report_argset_dump(configured_test_manager)
    all_text = "".join(lines[2:-1])
    assert "<" not in all_text
    assert ">" not in all_text


def test_reportable_render_uses_qualified_name_in_title(configured_test_manager):
    """Reportable rendering should use the fully qualified name in the link and the title"""

    @cf.stage(None, ["test_output"], [PickleCacher])
    def basic_reportable(record):
        record.report(JsonReporter({"test": "hello world"}))
        return "test"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    basic_reportable(r0)

    reportable = configured_test_manager.reportables[0]
    html = render_reportable(
        reportable, configured_test_manager, configured_test_manager.cache_path
    )
    assert reportable.qualified_name in html[1]  # link
    assert reportable.qualified_name in html[2]  # title


def test_detailed_record_subgraph_aggregate_doesnot_include_previous_artifacts(
    configured_test_manager,
):
    """A detailed subgraph map for an aggregate shouldn't show the nameless artifact
    nodes that are coming from other records."""

    @cf.stage(None, ["test_output"])
    def test(record):
        return "test"

    @cf.aggregate(inputs=["test_output"], outputs=["final"])
    def agg(record, records, test_output):
        return "things"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test1"))
    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test2"))
    r2 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test3"))

    test(r0)
    test(r1)
    agg(r2, [r0, r1])

    dot = Digraph()
    dot.attr(compound="true")
    dot.attr(nodesep=".2")
    dot.attr(ranksep=".2")

    _add_record_subgraph(dot, 2, r2, configured_test_manager)

    # count connections
    conn_count = 0
    for line in dot.body:
        if "->" in line:
            conn_count += 1
    assert conn_count == 1
