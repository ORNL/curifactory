import os
from dataclasses import dataclass
from enum import IntEnum

import pandas as pd
from graphviz import Digraph

import curifactory as cf
from curifactory import reporting
from curifactory.caching import JsonCacher, PickleCacher
from curifactory.experiment import run_experiment
from curifactory.reporting import (
    JsonReporter,
    LatexTableReporter,
    _add_record_subgraph,
    render_reportable,
)


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


def test_preview_gets_used_for_lazy_cached_artifact_reuse(configured_test_manager):
    """A run that re-uses a lazy cached artifact from a previous run should still display
    its preview string correctly in the output map."""

    @cf.stage(None, [cf.Lazy("Things")], [PickleCacher])
    def do_thing(record):
        return "needle in a haystack"

    r0 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    do_thing(r0)

    r1 = cf.Record(configured_test_manager, cf.ExperimentParameters(name="test"))
    do_thing(r1)

    dot0 = Digraph()
    _add_record_subgraph(dot0, 0, r0, configured_test_manager)

    dot1 = Digraph()
    _add_record_subgraph(dot1, 1, r1, configured_test_manager)

    assert "(str) needle in a haystack" in dot0.body[6]
    assert "(str) needle in a haystack" in dot1.body[6]


def test_fallback_css_used(configured_test_manager):
    """If the report css file is missing, it should use the one that comes with the cf package."""

    configured_test_manager.generate_report()
    assert os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/style.css"
    )


def test_all_relevant_reports_generated(configured_test_manager):
    """When a store full run of an experiment occurs, the regular report should exist, the linked
    "_latest" should exist, and the full store output should have a copy."""

    configured_test_manager.store_full = True
    run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        mngr=configured_test_manager,
        store_full=True,
    )

    assert os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/index.html"
    )

    assert os.path.exists(f"{configured_test_manager.reports_path}/_latest/index.html")

    assert os.path.exists(
        f"{configured_test_manager.get_run_output_path()}/report/index.html"
    )


def test_no_report_generated_when_no_report_flag(configured_test_manager):
    """When the `--no-report` flag is used, running the experiment shouldn't generate a report."""

    configured_test_manager.store_full = True
    run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        mngr=configured_test_manager,
        store_full=True,
        report=False,
    )

    assert not os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/index.html"
    )

    assert not os.path.exists(
        f"{configured_test_manager.reports_path}/_latest/index.html"
    )

    assert not os.path.exists(
        f"{configured_test_manager.get_run_output_path()}/report/index.html"
    )


def test_log_copied_to_report(configured_test_manager):
    """A copy of the log should be included in the report folder."""
    configured_test_manager.store_full = True
    run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        mngr=configured_test_manager,
        store_full=True,
    )

    assert os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/log.txt"
    )

    assert os.path.exists(f"{configured_test_manager.reports_path}/_latest/log.txt")

    assert os.path.exists(
        f"{configured_test_manager.get_run_output_path()}/report/log.txt"
    )


def test_image_reporter_persists_after_original_deletion(configured_test_manager):
    """The ImageReporter should still display the image in a report for a re-run
    experiment, even if the original image was deleted."""

    run_experiment("image_reporter", ["image_reporter"], mngr=configured_test_manager)
    assert os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/reportables/test_save_manual_image_0.png"
    )

    os.remove("testing.png")

    run_experiment("image_reporter", ["image_reporter"], mngr=configured_test_manager)
    assert os.path.exists(
        f"{configured_test_manager.reports_path}/{configured_test_manager.get_reference_name()}/reportables/test_save_manual_image_0.png"
    )


def test_latex_table_reporter():
    """The LatexTableReporter should correctly...output a latex table? This is just
    a basic functionality test."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    r = LatexTableReporter(df)
    assert r.html() == [
        "<pre>",
        "\\begin{tabular}{lrr}\n & a & b \\\\\n0 & 1 & 4 \\\\\n1 & 2 & 5 \\\\\n2 & 3 & 6 \\\\\n\\end{tabular}\n",
        "</pre>",
    ]
