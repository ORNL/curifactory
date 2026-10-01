import re
import textwrap
from pathlib import Path

from curifactory import Record, stage
from curifactory.caching import Cacheable, JsonCacher


def documented_classes():
    page = Path(__file__).parents[1] / "sphinx" / "source" / "user" / "cache.rst"
    section = page.read_text().split("Metadata\n--------", 1)[1]
    section = section.split("Lazy cache objects", 1)[0]
    blocks = re.findall(r"\.\. code-block:: python\n\n((?:    [^\n]*\n|\n)+)", section)
    result = []
    for block in blocks:
        namespace = {"Cacheable": Cacheable, "JsonCacher": JsonCacher}
        exec(textwrap.dedent(block), namespace)
        result.append(namespace["UsesExtraMetadataCacher"])
    assert len(result) == 2
    return result


def test_metadata_example_with_automatic_stage_metadata(
    configured_test_manager, sample_args, tmp_path
):
    example = documented_classes()[0]

    @stage([], ["value"], [example(str(tmp_path / "automatic.json"))])
    def create_value(record):
        return {"value": 42}

    create_value(Record(configured_test_manager, sample_args))
    reloaded = create_value(Record(configured_test_manager, sample_args))
    assert reloaded.state["value"] == {"value": 42}


def test_metadata_example_with_explicit_inline_metadata(tmp_path):
    example = documented_classes()[1]
    path = str(tmp_path / "inline.json")
    example(path).save({"value": 42})
    assert example(path).load() == {"value": 42}
