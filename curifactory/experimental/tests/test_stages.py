from curifactory.experimental.artifact import Artifact
from curifactory.experimental.stage import Stage, stage


def test_basic_stage_def():
    """A stage with no outputs should still work."""

    @stage()
    def do_nothing():
        return None

    s = do_nothing()
    assert isinstance(s, Stage)
    s()


def test_stage_with_return():
    """A stage with a return should return a populated Stage object."""

    @stage(Artifact("thing"))
    def return_thing():
        return 5

    s1 = return_thing()
    assert hasattr(s1, "thing")
    assert isinstance(s1.thing, Artifact)
    output = s1()
    assert output.obj == 5


def test_multiple_of_same_stage_should_return_diff_artifacts():
    """Having multiple instances of a stage should be returning a new
    artifact each time, to avoid weird mutability problems."""

    @stage(Artifact("thing"))
    def return_thing():
        return 5

    s1 = return_thing()
    s2 = return_thing()

    assert s1.thing != s2.thing
    assert s1.outputs == s1.thing
    assert s2.outputs == s2.thing
    assert s1.outputs != s2.outputs
