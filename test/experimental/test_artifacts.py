from curifactory.experimental.artifact import Artifact
from curifactory.experimental.pipeline import pipeline
from curifactory.experimental.staging import stage


def test_artifact_siblings_not_in_dependencies(test_manager):
    """An output from a stage should not have other outputs of that same stage in its dependencies."""

    @stage(Artifact("t0"))
    def gett0():
        return 5

    @stage(Artifact("t1"), Artifact("t2"))
    def t1andt2(t0):
        return t0 + 1, t0 + 2

    @pipeline
    def test():
        t0 = gett0()
        t1, t2 = t1andt2(t0)

    thing = test("thing")
    assert thing.artifacts.t1[0] not in thing.artifacts.t2[0].dependencies()
    assert thing.artifacts.t2[0] not in thing.artifacts.t1[0].dependencies()
    assert thing.artifacts.t0[0] in thing.artifacts.t1[0].dependencies()
    assert thing.artifacts.t0[0] in thing.artifacts.t2[0].dependencies()
