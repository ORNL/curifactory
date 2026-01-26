import pytest

from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import Pipeline, pipeline
from curifactory.experimental.stage import Stage, stage


@pytest.fixture()
def add_things_pipeline(test_manager):
    @stage(Artifact("thing1"))
    def get_thing1(start_num: int = 5):
        return start_num

    @stage(Artifact("thing2"))
    def get_thing2(thing1, next_num: int = 3):
        return thing1 + next_num

    @pipeline
    def add_things(num1: int = 2, num2: int = 7):
        t1 = get_thing1(num1).outputs
        t2 = get_thing2(t1, num2).outputs
        return t2

    return add_things


def test_basic_pipeline(test_manager, add_things_pipeline):
    """A stage that takes an input from another stage should resolve correctly."""
    p1 = add_things_pipeline("p1", num1=2, num2=7)
    p1.run()
    assert p1.outputs.obj == 9


def test_artifact_hashes_are_different(test_manager, add_things_pipeline):
    """Hash strings of artifacts produced from different parameters (including from previous stages) should be different"""
    p1 = add_things_pipeline("p1", num1=2, num2=7)
    p2 = add_things_pipeline("p2", num1=8, num2=7)

    p1.run()
    p2.run()

    assert p1.artifacts[0].hash_str != p2.artifacts[0].hash_str
    assert p1.artifacts[1].hash_str != p2.artifacts[1].hash_str

    assert p1.artifacts[0].hash_str != p1.artifacts[1].hash_str


def test_replacing_prior_artifact(test_manager, add_things_pipeline):
    """Replacing an artifact should update subsequent computation and hashes."""

    p1 = add_things_pipeline("p1", num1=2, num2=7)
    p2 = add_things_pipeline("p2", num1=8, num2=7)

    p2.artifacts.thing1[0].replace(p1.artifacts.thing1[0].copy())

    p2.run()
    assert p2.outputs.obj == 9
    assert p2.artifacts[1].hash_str == p1.artifacts[1].hash_str

    assert p2.artifacts[1] != p1.artifacts[1]


def test_pipeline_of_pipelines_makes_artifact_copies(test_manager, add_things_pipeline):
    """When pipelines are used as parameters in other pipelines, any artifacts should be copies"""

    @stage(Artifact("thing3"))
    def final_add(prev_value, next_value):
        return prev_value + next_value

    @pipeline
    def add_another_thing(prev_pipe, new_num: int = 11):
        prev = prev_pipe.outputs
        final = final_add(prev, new_num).outputs
        return final

    p1 = add_things_pipeline("p1", num1=2, num2=7)
    p2 = add_another_thing("p2", prev_pipe=p1, new_num=1)

    p2.run()
    assert p2.outputs.obj == 10
    assert p2.outputs.compute.artifacts[0] != p1.outputs
    assert (
        p2.outputs.compute.artifacts[0].compute_hash()[0]
        == p1.outputs.compute_hash()[0]
    )
