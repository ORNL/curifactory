import curifactory as cf
from curifactory.reporting import JsonReporter
from curifactory.caching import JsonCacher
import os


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
