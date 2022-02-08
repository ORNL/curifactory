Configuration and directory structure
=====================================

Project directories
-------------------

Curifactory expects the following directory structure by default:

- :code:`data/`

    - :code:`cache/`: all cached intermediate data
    - :code:`runs/`: full runs from :code:`--store-full`
- :code:`docker/`: (not required if no intention of creating docker images with :code:`--docker`)
- :code:`experiments/`: the runnable experiment scripts
- :code:`logs/`: all logging files from experiment runs, organized by reference name (experiment name, run number, timestamp)
- :code:`notebooks/`: (not required if no intention of creating notebooks with :code:`--notebook`)

    - :code:`experiments/`: the output notebooks from running experiments with :code:`--notebook` are stored here.
- :code:`params`: the parameter scripts for experiments
- :code:`reports/`: output HTML reports from each experiment run.


Configuration
-------------

Curifactory allows you to change the default paths where various components
are stored in your project, by setting them in a :code:`curifactory_config.json`
file in the project root.

The default values for the configuration are shown in this example:

.. code-block:: json

    {
        "experiments_module_name": "experiments",
        "params_module_name": "params",
        "manager_cache_path": "data/",
        "cache_path": "data/cache",
        "runs_path": "data/runs",
        "logs_path": "logs/",
        "notebooks_path": "notebooks/",
        "reports_path": "reports/",
        "report_css_path": "reports/style.css",
    }

:code:`experiments_module_name` - the name of the folder where experiment
scripts are stored. This is treated as a python module, running an experiment
essentially runs :code:`import experiments.[experiment_script_name]`

:code:`params_module_name` - the name of the folder where parameter scripts
are kept.

:code:`manager_cache_path` - The folder where artifact manager data is kept,
namely the experiment store.

:code:`cache_path` - The directory used for caching all stage outputs.

:code:`runs_path` - The directory where full runs are saved with the
:code:`--store-full` flag, see :ref:`Full stores`.

:code:`logs_path` - The directory where every experiment run log file is stored.

:code:`notebooks_path` - The directory where every output notebooks from
experiments run with :code:`--notebook` are stored.

:code:`reports_path` - The directory where every experiment run report is
generated.

:code:`report_css_path` - The CSS file to copy into each report directory. A default
stylesheet comes with the cookiecutter project
`cookiecutter project <https://github.com/ORNL/cookiecutter-curifactory>`_
