from test.experimental.pipelines.example import add_things, run_w_stage_depends

from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.stage import stage


def test_basic_pipeline(test_manager):
    """A stage that takes an input from another stage should resolve correctly."""
    p1 = add_things("p1", num1=2, num2=7)
    p1.run()
    assert p1.outputs.obj == 9


def test_artifact_hashes_are_different(test_manager):
    """Hash strings of artifacts produced from different parameters (including from previous stages) should be different"""
    p1 = add_things("p1", num1=2, num2=7)
    p2 = add_things("p2", num1=8, num2=7)

    p1.run()
    p2.run()

    assert p1.artifacts[0].hash_str is not None
    assert p2.artifacts[0].hash_str is not None

    assert p1.artifacts[0].hash_str != p2.artifacts[0].hash_str
    assert p1.artifacts[1].hash_str != p2.artifacts[1].hash_str

    assert p1.artifacts[0].hash_str != p1.artifacts[1].hash_str


def test_replacing_prior_artifact(test_manager):
    """Replacing an artifact should update subsequent computation and hashes."""

    p1 = add_things("p1", num1=2, num2=7)
    p2 = add_things("p2", num1=8, num2=7)

    # p2.artifacts.thing1[0].replace(p1.artifacts.thing1[0].copy())
    p2.artifacts.thing1[0].replace(p1.artifacts.thing1[0].copy())

    p2.run()
    assert p2.outputs.obj == 9
    assert p2.artifacts[1].hash_str == p1.artifacts[1].hash_str

    assert p2.artifacts[1] != p1.artifacts[1]


def test_pipeline_of_pipelines_makes_artifact_copies(test_manager):
    """When pipelines are used as parameters in other pipelines, any artifacts should be copies"""

    @stage(Artifact("thing3"))
    def final_add(prev_value, next_value):
        return prev_value + next_value

    @pipeline
    def add_another_thing(prev_pipe, new_num: int = 11):
        prev = prev_pipe.outputs
        final = final_add(prev, new_num).outputs
        return final

    p1 = add_things("p1", num1=2, num2=7)
    p2 = add_another_thing("p2", prev_pipe=p1, new_num=1)

    p2.run()
    assert p2.outputs.obj == 10
    assert p2.outputs.compute.artifacts[0] != p1.outputs
    assert (
        p2.outputs.compute.artifacts[0].compute_hash()[0]
        == p1.outputs.compute_hash()[0]
    )


def test_pipeline_def_w_artifact_replacement(test_manager):
    """A pipeline that uses other pipelines and replaces artifacts within them should work and not break the original pipeline."""

    @pipeline
    def inconsistent_first_nums(pipe_one, pipe_two):
        return pipe_one.outputs, pipe_two.outputs

    @pipeline
    def consistent_first_nums(pipe_one, pipe_two):
        pipe_one.artifacts.thing1[0].replace(pipe_two.artifacts.thing1[0])
        return pipe_one.outputs, pipe_two.outputs

    p1 = add_things("p1", num1=2, num2=7)
    p2 = add_things("p2", num1=8, num2=9)

    p3 = inconsistent_first_nums("p3", p1, p2)
    p3.run()

    assert p3.outputs[0].obj == 9
    assert p3.outputs[1].obj == 17
    assert len(p3.artifacts.thing1) == 2

    p4 = consistent_first_nums("p4", p1, p2)
    p4.run()

    assert p4.outputs[0].obj == 15
    assert p4.outputs[1].obj == 17
    assert len(p4.artifacts.thing1) == 1

    p1.run()
    assert p1.artifacts.thing1[0].obj == 2
    assert p1.outputs.obj == 9


def test_pipeline_copy_retains_hashes(test_manager):
    """Before hash_str became a property there was an issue where hash_strs were sometimes None, which should never be the case"""
    p1 = add_things("p1", num1=2, num2=7)
    p1_copy = p1.copy()
    assert p1.artifacts.thing1[0].hash_str is not None
    assert p1_copy.artifacts.thing1[0].hash_str is not None


def test_pipeline_of_pipelines_first_stage_consolidation(test_manager):
    """When multiple pipelines come together and have similar stages those should be
    merged/replaced with a single one."""

    @pipeline
    def simple_aggregate(pipe1, pipe2):
        return pipe1.outputs, pipe2.outputs

    p1 = add_things("p1", num1=2, num2=7)
    p2 = add_things("p2", num1=2, num2=9)

    p3 = simple_aggregate("p3", p1, p2)
    assert len(p3.artifacts.thing1) == 1
    assert p3.artifacts.p2.thing1[0] == p3.artifacts.p1.thing1[0]

    p3.run()
    assert p3.outputs[0].obj == 9
    assert p3.outputs[1].obj == 11


def test_pipeline_that_returns_alists(test_manager):
    """A pipeline that returns a tuple of .outputs should work."""

    @stage(Artifact("things1"), Artifact("things2"))
    def do_multiple_things(a: int = 4):
        return a, a + 5

    @stage(Artifact("things3"), Artifact("things4"))
    def do_more_things(b: int = 6):
        return b, b + 6

    @pipeline
    def things(a, b):
        stage1 = do_multiple_things(a)
        stage2 = do_more_things(b)

        return stage1.outputs, stage2.outputs

    t = things("t", 4, 5)
    t.run()
    assert t.artifacts.things1[0].obj == 4
    assert t.artifacts.things2[0].obj == 9
    assert t.artifacts.things3[0].obj == 5
    assert t.artifacts.things4[0].obj == 11


def test_artifacts_from_before_stage_depends_should_show_up(test_manager):
    """Artifacts from before a stage with stage dependencies should still
    show up in a pipeline's artifact list."""

    p = run_w_stage_depends("p")
    print(p.outputs.artifacts)
    print(p.outputs.artifact_list())
    assert len(p.artifacts.something) > 0
