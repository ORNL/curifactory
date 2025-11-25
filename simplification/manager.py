"""Experiment and artifact manager"""

import importlib
import json
import logging
import os
import threading
from datetime import datetime
from uuid import uuid4

import duckdb


class _ManagerContext(threading.local):
    def __init__(self):
        self._manager: Manager = None

    @property
    def manager(self):
        if self._manager is None:
            self._manager = Manager.default_manager()
        return self._manager


MANAGER_CONTEXT = _ManagerContext()

CONFIGURATION_FILE = "curifactory_config.json"
"""The expected configuration filename."""
TIMESTAMP_FORMAT = "%Y-%m-%d-T%H%M%S"
"""The datetime format string used for timestamps in experiment run reference names."""


class Manager:
    def __init__(self, database_path: str = "data/store.db"):
        self.experiments = []

        self.database_path = database_path
        self.run_table = "cf_runs"

        self.logging_initialized: bool = False

        self._logger = None

        self.ensure_store_tables()

    def find_experiments_from_file(self, file_path: str):
        with self:
            importlib.import_module(file_path)

    def ensure_store_tables(self):
        with self.db_connection() as db:
            # TODO: have a cf_meta table with version info so we can record how
            # to upgrade database if schema changes
            db.sql(
                """
                CREATE TABLE IF NOT EXISTS cf_runs (
                    id UUID,
                    reference VARCHAR,
                    experiment_name VARCHAR,
                    run_number INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    succeeded BOOL,
                    commit VARCHAR,
                    dirty BOOL,
                    hostname VARCHAR,
                    user VARCHAR,
                    notes VARCHAR
                );
            """
            )

    # TODO: unclear if these should be associated with an experiment run instead
    # of an experiment or manager class
    def get_str_timestamp(self, experiment) -> str:
        """Convert the manager's run timestamp into a string representation."""
        return experiment.start_timestamp.strftime(TIMESTAMP_FORMAT)

    def get_reference_name(self, experiment) -> str:
        """Get the reference name of this run in the experiment registry.

        The format for this name is ``[experiment_name]_[run_number]_[timestamp]``."""
        return f"{experiment.name}_{experiment.run_number}_{self.get_str_timestamp(experiment)}"

    def get_next_experiment_run_number(self, experiment) -> int:
        with self.db_connection() as db:
            num = db.sql(
                "SELECT MAX(run_number) FROM cf_runs WHERE experiment_name = $experimentname",
                params=dict(experimentname=experiment.name),
            ).fetchone()[0]
            if num is None:
                num = 0
            return num + 1

    # TODO: is it worth having an experiment_run object?
    def add_experiment_run(self, experiment):
        experiment_id = uuid4()  # TODO: should base on reference name?
        run_num = self.get_next_experiment_run_number(experiment)

        experiment.db_id = experiment_id
        experiment.run_number = run_num
        experiment.start_timestamp = datetime.now()
        experiment.reference = self.get_reference_name(experiment)

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_runs (
                        id,
                        reference,
                        experiment_name,
                        run_number,
                        start_time
                    )
                    VALUES (?, ?, ?, ?, ?)
                """,
                [
                    experiment_id,
                    experiment.reference,
                    experiment.name,
                    experiment.run_number,
                    experiment.start_timestamp,
                ],
            )

    def complete_experiment_run(self, experiment):
        experiment.end_timestamp = datetime.now()
        with self.db_connection() as db:
            db.sql(
                """UPDATE cf_runs SET end_time = $endtime, WHERE ID = $id""",
                params=dict(endtime=experiment.end_timestamp, id=experiment.db_id),
            )

    def db_connection(self):
        return duckdb.connect(self.database_path)

    @property
    def logger(self):
        # TODO: what about logging_initialized?
        if self._logger is None:
            # self.init_cf_logging()
            self.init_logging()
        return self._logger

    def init_root_logging(self):
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

    def init_cf_logging(self):
        cf_logger = logging.getLogger("curifactory")
        # cf_logger.setLevel(logging.INFO)
        cf_logger.setLevel(logging.DEBUG)
        # NOTE: see https://docs.python.org/3/howto/logging.html#library-config
        # probably don't add a handler by default?
        cf_logger.addHandler(logging.StreamHandler())
        self._logger = cf_logger

    def init_logging(self):
        # set up root logging
        # self.init_root_logging()
        # set cf specific logging
        self.init_cf_logging()

        # NOTE: if need to disable, use addHandler(logging.NullHandler())

        self.logging_initialized = True

    @classmethod
    def get_manager(cls):
        return MANAGER_CONTEXT.manager

    def __enter__(self):
        MANAGER_CONTEXT._manager = self

    def __exit__(self, exc_type, exc_value, traceback):
        MANAGER_CONTEXT._manager = None

    @staticmethod
    def default_manager():
        """Try to find a config file and if not assume some defaults."""
        # try to find a configuration file in this dir or parent dirs
        search_depth = 3
        prefix = ""
        while not os.path.exists(f"{prefix}{CONFIGURATION_FILE}") and search_depth > 0:
            prefix += "../"
            search_depth -= 1

        if os.path.exists(f"{prefix}{CONFIGURATION_FILE}"):
            with open(f"{prefix}{CONFIGURATION_FILE}") as infile:
                config = json.load(infile)
        else:
            config = {"database_path": "data/store.db"}
        return Manager.from_config(config)

    @staticmethod
    def from_config(config: dict):
        # Allow specifying a python module with a get_manager(config) function
        # that returns a populated manager. (Allows subclassing a manager to
        # override stuff like logging etc.)
        if "manager_module" in config:
            try:
                manager_module = importlib.import_module(config["manager_module"])
            except ImportError:
                raise f"Could not import a manager module from config \"{config['manager_module']}\""
            return manager_module.get_manager(config)
        return Manager(**config)
