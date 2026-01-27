"""Tests for string to artifact/pipeline/reference conversion, primarily important for CLI usage"""


def test_var_resolution(test_manager):
    """Resolving a string referring to a variable name of an instantiated pipeline should correctly return that pipeline."""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("example1")
    assert "pipeline_instance" in resolutions
    assert resolutions["pipeline_instance"].name == "ex_one"

    assert "pipeline_instance_list" in resolutions
    assert len(resolutions["pipeline_instance_list"]) == 1


def test_var_list_resolution(test_manager):
    """A string that could describe multiple variable names should just return the list of pipelines."""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("example")
    assert "pipeline_instance_list" in resolutions
    assert "example1" in resolutions["pipeline_instance_list"]
    assert "example2" in resolutions["pipeline_instance_list"]


def test_var_w_module_resolution(test_manager):
    """Passing a string that includes the module should still resolve correctly to that pipeline."""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("example.example1")
    assert "pipeline_instance" in resolutions
    assert resolutions["pipeline_instance"].name == "ex_one"

    assert "pipeline_instance_list" in resolutions
    assert len(resolutions["pipeline_instance_list"]) == 1


def test_name_resolution(test_manager):
    """Resolving a string referring to a pipeline instance by name should correctly return that pipeline."""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("ex_one")
    assert "pipeline_instance" in resolutions
    assert resolutions["pipeline_instance"].name == "ex_one"

    assert "pipeline_instance_list" in resolutions
    assert len(resolutions["pipeline_instance_list"]) == 1


def test_artifact_name_resolution(test_manager):
    """Requesting a specific artifact should return just that artifact."""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("ex_one.thing1")
    assert "artifact" in resolutions
    assert resolutions["artifact"].name == "thing1"


def test_artifact_from_stage_resolution(test_manager):
    """Requesting an artifact by stage name with single output artifact should return that artifact"""
    test_manager.load_default_pipeline_imports()
    resolutions = test_manager.resolve_reference("ex_one.get_thing1")
    print(resolutions)
    assert "artifact" in resolutions
    assert resolutions["artifact"].name == "thing1"
