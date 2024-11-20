from curifactory.experiment import run_experiment
from curifactory.store import SQLStore


def test_add_run(configured_test_manager):
    store = SQLStore(configured_test_manager.manager_cache_path)

    results, mngr = run_experiment(
        "simple_cache",
        ["simple_cache"],
        param_set_names=["thing1", "thing2"],
        mngr=configured_test_manager,
    )

    store.add_run(mngr)
