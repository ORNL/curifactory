import pytest


def test_import_module_w_error(test_manager):
    """Importing a broken module should fail"""
    with pytest.raises(ModuleNotFoundError):
        test_manager.quietly_import_module(
            "test.experimental.pipelines.broken.something"
        )


def test_bad_import_gets_added_to_failed_imports(test_manager):
    """When an import from import_pipelines_from_module fails,
    it should be added to the dictionary"""
    test_manager.import_pipelines_from_module(
        "test.experimental.pipelines.broken.something"
    )
    print(test_manager.failed_imports)
    assert "test.experimental.pipelines.broken.something" in test_manager.failed_imports
