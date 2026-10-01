import importlib.util
from pathlib import Path

import pytest

from curifactory import Record


@pytest.mark.parametrize("remove_expensive", [False, True])
def test_documented_partial_cache_example(
    configured_test_manager, sample_args, remove_expensive
):
    path = Path(__file__).parents[1] / "examples" / "partial_stage_cache.py"
    spec = importlib.util.spec_from_file_location("partial_cache_example", path)
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    calls = {"expensive": 0, "other": 0}

    def compute_expensive():
        calls["expensive"] += 1
        return 499500

    def compute_other():
        calls["other"] += 1
        return "ready"

    example.compute_expensive = compute_expensive
    example.compute_other = compute_other
    example.make_pair(Record(configured_test_manager, sample_args))
    cache = Path(configured_test_manager.cache_path)
    other_paths = list(cache.glob("*other_result.pkl"))
    assert len(other_paths) == 1
    other_paths[0].unlink()
    if remove_expensive:
        expensive_paths = list(cache.glob("*expensive_result.pkl"))
        assert len(expensive_paths) == 1
        expensive_paths[0].unlink()

    record = example.make_pair(Record(configured_test_manager, sample_args))
    assert record.state["expensive_result"] == 499500
    assert record.state["other_result"] == "ready"
    expected_calls = {"expensive": 2 if remove_expensive else 1, "other": 2}
    assert calls == expected_calls

    example.make_pair(Record(configured_test_manager, sample_args))
    assert calls == expected_calls
