from test.experimental.pipelines.example import add_thingsc

from curifactory.experimental.pipeline import PipelineFromRef


def test_basic_caching_when_exactly_rerun(clear_filesystem, test_manager):
    """No compute should run when everything is cached."""
    p1 = add_thingsc("p1", 3, 4)
    p2 = add_thingsc("p2", 3, 4)

    p1.run()
    assert p1.artifacts.thing1[0].compute.computed
    assert p1.artifacts.thing2[0].compute.computed

    p2.run()
    assert not p2.artifacts.thing1[0].compute.computed
    assert not p2.artifacts.thing2[0].compute.computed

    assert p1.outputs.obj == p2.outputs.obj


def test_basic_caching_when_first_stage_similar(clear_filesystem, test_manager):
    """When only one early stage is the same that cache should be used."""
    p1 = add_thingsc("p1", 3, 4)
    p2 = add_thingsc("p2", 3, 6)

    p1.run()
    assert p1.artifacts.thing1[0].compute.computed
    assert p1.artifacts.thing2[0].compute.computed

    p2.run()
    assert not p2.artifacts.thing1[0].compute.computed
    assert p2.artifacts.thing2[0].compute.computed

    assert p1.outputs.obj == 7
    assert p2.outputs.obj == 9


def test_basic_caching_when_first_stage_different(clear_filesystem, test_manager):
    """When an earlier stage is different, downstream stages should NOT use cache"""
    p1 = add_thingsc("p1", 3, 4)
    p2 = add_thingsc("p2", 6, 4)

    p1.run()
    assert p1.artifacts.thing1[0].compute.computed
    assert p1.artifacts.thing2[0].compute.computed

    p2.run()
    assert p2.artifacts.thing1[0].compute.computed
    assert p2.artifacts.thing2[0].compute.computed

    assert p1.outputs.obj == 7
    assert p2.outputs.obj == 10


def test_caching_from_db_ref_works(clear_filesystem, test_manager):
    """Loading and "running" a reference from db should correctly pick up cache stuff"""
    p1 = add_thingsc("p1", 3, 4)
    p1.run()

    run_ref = test_manager.runs.reference[0]
    p2 = PipelineFromRef(run_ref)
    p2.run()

    assert not p2.artifacts.thing1[0].compute.computed
    assert not p2.artifacts.thing2[0].compute.computed
    assert p2.outputs.obj == 7
