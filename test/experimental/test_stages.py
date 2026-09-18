from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.staging import Stage, stage


def test_basic_stage_def(test_manager):
    """A stage with no outputs should still work."""

    @stage()
    def do_nothing():
        return None

    s = do_nothing().stage
    assert isinstance(s, Stage)
    s()


def test_stage_with_return(test_manager):
    """A stage with a return should return a populated Stage object."""

    @stage(Artifact("thing"))
    def return_thing():
        return 5

    s1 = return_thing().stage
    assert hasattr(s1, "thing")
    assert isinstance(s1.thing, Artifact)
    output = s1()
    assert output.obj == 5


def test_multiple_of_same_stage_should_return_diff_artifacts(test_manager):
    """Having multiple instances of a stage should be returning a new
    artifact each time, to avoid weird mutability problems."""

    @stage(Artifact("thing"))
    def return_thing():
        return 5

    s1 = return_thing().stage
    s2 = return_thing().stage

    assert s1.thing != s2.thing
    assert s1.outputs == s1.thing
    assert s2.outputs == s2.thing
    assert s1.outputs != s2.outputs


def test_stage_that_passes_self(test_manager):
    """Having a stage that passes self should work and not break hashing/input parameters
    (specifically during hashing, the stage parameters doesn't line up with args because of
    first self param that isn't passed by user directly (which is what fills args))
    """

    @stage(Artifact("thing"), pass_self=True)
    def selfish(self, t1, t2):
        assert isinstance(self, Stage)
        assert self.artifacts[0].name == "thing1"
        assert self.artifacts[1].name == "thing2"
        assert self.outputs.name == "thing"
        return t1 + t2

    @stage(Artifact("thing1"))
    def gett1():
        return 1

    @stage(Artifact("thing2"))
    def gett2():
        return 2

    @pipeline
    def getallthings():
        t1 = gett1()
        t2 = gett2()
        s3 = selfish(t1, t2).stage

        assert list(s3.parameter_kinds.keys())[0] != "self"
        assert list(s3.parameter_defaults.keys())[0] != "self"
        assert list(s3.parameter_positions.keys())[0] != "self"
        assert s3.parameter_positions[list(s3.parameter_positions.keys())[0]] == 0
        assert list(s3.parameter_positions.keys())[0] == "t1"

    test = getallthings("test")
    test.run()
