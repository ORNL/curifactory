from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.staging import stage


def test_artifact_siblings_not_in_dependencies(test_manager):
    """An output from a stage should not have other outputs of that same stage in its dependencies."""

    @stage(Artifact("t0"), Artifact("what"))
    def gett0():
        return 5, "thing"

    @stage(Artifact("t1"), Artifact("t2"))
    def t1andt2(t0):
        return t0 + 1, t0 + 2

    @pipeline
    def test():
        t0, _ = gett0()
        t1, t2 = t1andt2(t0)

    thing = test("thing")
    assert thing.artifacts.t1[0] not in thing.artifacts.t2[0].dependencies()
    assert thing.artifacts.t2[0] not in thing.artifacts.t1[0].dependencies()
    assert thing.artifacts.t0[0] in thing.artifacts.t1[0].dependencies()
    assert thing.artifacts.t0[0] in thing.artifacts.t2[0].dependencies()

    assert len(thing.artifacts.what) > 0


def test_getting_unused_output_artifacts_from_previous_pipeline(test_manager):
    @stage(Artifact("t0"))
    def gett0():
        return 5

    @stage(Artifact("t1"), Artifact("t2"))
    def t1andt2(t0, num):
        return t0 + 1, t0 + num

    @pipeline
    def test(num: int = 2):
        t0 = gett0()
        t1, t2 = t1andt2(t0, num)

        return t2

    @stage(Artifact("t3"))
    def gett3(t2):
        return t2 + 199

    @pipeline
    def test2(prev_pipeline: test):
        t3 = gett3(prev_pipeline.artifacts.t2[0])
        return t3

    test_0 = test("test_0")
    test_1 = test2("test_1", test_0)

    assert len(test_1.artifacts.t1) > 0
