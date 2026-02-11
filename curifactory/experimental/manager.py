"""Pipeline and artifact manager"""

import importlib
import json
import logging
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb
import pandas as pd
from jinja2 import ChoiceLoader, DictLoader, Environment
from rich import get_console
from rich.logging import RichHandler

import curifactory.experimental as cf


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
"""The datetime format string used for timestamps in pipeline run reference names."""


class Manager:
    def __init__(
        self,
        database_path: str = "data/store.db",
        cache_path: str = "data/cache",
        reports_path: str = "reports",
        default_pipeline_modules: list[str] = None,
        **additional_configuration,
    ):
        self._pipeline_defining_stack = []
        """Use this to capture context of stages etc."""

        self.pipelines = {}
        """dictionary of pipeline dataclasses keyed by dataclass name."""
        self.parameterized_pipelines = {}
        """Dictionary of initialized (parameterized) pipelines keyed by dataclass type"""
        self.pipeline_ref_names = {}
        """Dictionary of possible names/references to use to refer to specific pipelines."""
        self.imported_module_names = []
        """List of module strings that have been successfully imported and parsed for pipelines."""
        self.failed_imports = {}
        """Dictionary of import module strings and tuples of the exceptions that were raised and tracebacks."""

        # ---- configuration ----
        self.database_path = database_path
        # self.run_table = "cf_run"  # TODO: not used yet

        self.cache_path = cache_path

        self.reports_path = reports_path

        self.repr_functions: dict[type, callable] = {
            duckdb.DuckDBPyRelation: lambda obj: f"(duckdb) {len(obj)} rows",
            pd.DataFrame: lambda obj: f"(pandas) {len(obj)} rows",
        }

        self.jinja_templates = {
            "default.html": """
            <html>
                <head>
                    <style>
                    {% include "style.css" %}
                    </style>
                </head>
                <body>
                    <h1>{{ reference_name }}</h1>
                    <h3>Pipeline: {{ pipeline_name }}</h3>

                    {% include "metadata.html" %}

                    <h2>Reportables</h2>
                    {% for reportable in reportables %}
                        {% include "reportable.html" %}
                    {% endfor %}

                    <h2>Pipeline map</h2>
                    {{ map }}

                    <h2>Parameters</h2>
                    <pre>
{{ parameters }}
                    </pre>
                </body>
            </html>
            """,
            "style.css": """
                .reportable {
                    border: 1px solid gray;
                    display: inline-block;
                    vertical-align: top;
                    padding: 5px;
                    padding-top: 0px;
                    padding-bottom: 0px;
                }
            """,
            "reportable.html": """
                <div class='reportable'>
                    <a name='{{ reportable.name }}'></a>
                    <h3>{{ reportable.name }}</h3>
                    {{ reportable.html }}
                </div> <!-- /reportable -->
            """,
            "metadata.html": """
                <div class='metadata_block'>
                    <ul>
                    {% for key, value in pipeline_metadata.items() %}
                        <li><b>{{ key }}</b> - {{ value }}</li>
                    {% endfor %}
                    </ul>
                </div>
            """,
        }

        self.default_pipeline_modules: list[str] = default_pipeline_modules

        self.additional_configuration: dict[str, Any] = additional_configuration
        """Anything in additional configuration can be accessed/referenced in stages"""
        # ---- /configuration ----

        self.current_pipeline_run = None
        self.current_pipeline_run_target = None
        self.current_stage = None
        self.currently_recording: bool = False

        self.error_state: bool = False

        self.logging_initialized: bool = False
        self._logger = None

        self._sys_paths_added: bool = False
        self.project_root: str = None

        self.jinja_environment = None

        self.ensure_dir_paths()
        self.ensure_store_tables()
        self.ensure_sys_path()

        self._default_imports = False
        # self.load_default_pipeline_imports()

    @property
    def config(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "cache_path": self.cache_path,
            "default_pipeline_modules": self.default_pipeline_modules,
            **self.additional_configuration,
        }

    @property
    def runs(self) -> pd.DataFrame:
        with self.db_connection() as db:
            return db.sql("SELECT * FROM cf_run").df()

    def load_jinja_env(self):
        self.jinja_environment = Environment(
            loader=ChoiceLoader(
                [
                    DictLoader(self.jinja_templates)
                    # FileSystemLoader ...
                ]
            ),
            autoescape=False,
        )

    def resolve_reference(self, ref_str: str, types: list[str] = None):
        # possible types:
        # * module
        # * module list?
        # * pipeline class
        # * pipeline class list
        # * pipeline instance
        # * pipeline instance list
        # * mixed pipeline class/instance list?
        # * artifact
        # * artifact list
        # * stage
        # * cacher_path --> artifact
        # * pipeline reference name (db)

        resolutions = {}
        # TODO: have an "exact_match" key which is a list of the other keys in
        # which there is an exact (and not just partial/filter) match

        # TODO: check for path (if contains '/'?)

        if (
            types is None
            or "module" in types
            or "pipeline" in types
            or "pipeline_instance" in types
            or "pipeline_instance_list" in types
            or "pipeline_class" in types
            or "pipeline_class_list" in types
        ):
            reference_parts = self.divide_reference_parts(ref_str)
            print("ref parts", reference_parts)
            if reference_parts["module"] is not None:
                if "module" not in resolutions:
                    resolutions["module"] = []
                resolutions["module"].append(reference_parts["module"])

            if reference_parts["pipeline"] is not None:
                if reference_parts["pipeline"] in self.pipeline_ref_names:
                    resolutions["pipeline_instance"] = self.pipeline_ref_names[
                        reference_parts["pipeline"]
                    ]
                if reference_parts["pipeline"] in self.pipelines:
                    resolutions["pipeline_class"] = self.pipelines[
                        reference_parts["pipeline"]
                    ]

                resolutions["pipeline_instance_list"] = {
                    name: self.pipeline_ref_names[name]
                    for name in self.pipeline_ref_names.keys()
                    if name.startswith(reference_parts["pipeline"])
                }
                # TODO: class list should also be based on module if pipeline is ""
                resolutions["pipeline_class_list"] = [
                    self.pipelines[name]
                    for name in self.pipelines.keys()
                    if name.startswith(reference_parts["pipeline"])
                ]

            if "pipeline_instance" in resolutions:
                # check for artifacts
                if reference_parts["artifact_filter"] is not None:
                    resolutions["artifact_list"] = resolutions[
                        "pipeline_instance"
                    ].artifacts.filter(reference_parts["artifact_filter"])
                    if len(resolutions["artifact_list"]) == 1:
                        resolutions["artifact"] = resolutions["artifact_list"][0]

        if types is None or "runs" in types:
            with self.db_connection() as db:
                # TODO: prob shouldn't be checking reference itself??
                ref_name_str = ref_str
                if "." in ref_name_str:
                    ref_name_str = ref_str[: ref_str.index(".")]
                references_df = db.sql(
                    f"SELECT * FROM cf_run WHERE starts_with(reference, '{ref_name_str}')"
                ).df()

            resolutions["reference_names"] = references_df.reference.values.tolist()
            if len(resolutions["reference_names"]) == 1:
                resolutions["reference_instance"] = cf.PipelineFromRef(
                    resolutions["reference_names"][0]
                )

            if (
                "pipeline_instance" not in resolutions
                and "reference_instance" in resolutions
            ):
                # if reference_parts["artifact_filter"] is not None:
                if "." in ref_str:
                    print("Yep!")
                    filter_str = ref_str[ref_str.index(".") + 1 :]
                    print(
                        "looking for artifacts filter string past reference: ",
                        filter_str,
                    )
                    resolutions["artifact_list"] = resolutions[
                        "reference_instance"
                    ].artifacts.filter(filter_str)
                    if len(resolutions["artifact_list"]) == 1:
                        resolutions["artifact"] = resolutions["artifact_list"][0]

            # resolutions["pipeline_instance_list"] = [
            #     self.pipeline_ref_names[name] for name in
            #     self.pipeline_keys_matching(reference_parts["pipeline"])
            # ]
        # if reference_parts["artifact_filter"] is not None:
        #
        #     if "artifact" not in resolutions:

        return resolutions

    def pipeline_keys_matching(self, prefix: str) -> list[str]:
        found = []
        for key in self.pipeline_ref_names.keys():
            if key.startswith(prefix):
                found.append(key)
        return found

    def load_default_pipeline_imports(self):
        if self._default_imports:
            return
        if self.default_pipeline_modules is not None:
            for module in self.default_pipeline_modules:
                self.import_pipelines_from_module(module)
        self._default_imports = True

    def import_pipelines_from_module(self, module_str: str) -> str:
        # try to load the module
        self.logger.debug(f"Attempting to import {module_str}")
        try:
            module = self.quietly_import_module(module_str)
        except Exception as e:
            self.failed_imports[module_str] = (e, traceback.format_exc())
            return ""
        remainder = None
        while module is None:
            if remainder is None:
                remainder = module_str.split(".")[-1]
            else:
                remainder = module_str.split(".")[-1] + f".{remainder}"

            if "." not in module_str:
                # TODO: error? or no?
                return remainder
            # keep going "up" a . to try to find a valid module
            module_str = ".".join(module_str.split(".")[:-1])
            try:
                module = self.quietly_import_module(module_str)
            except Exception as e:
                self.failed_imports[module_str] = (e, traceback.format_exc())
                return ""

        self.imported_module_names.append(module_str)

        # parse through all the things in the module looking for pipelines and
        # pipeline classes
        for attr in dir(module):
            value = getattr(module, attr)
            if isinstance(value, cf.Pipeline):
                self.add_pipeline_to_ref_names(module_str, attr, value)
            # check for pipeline types
            elif type(value).__name__ == "PipelineFactoryWrapper":
                # check if making a default is possible
                can_make_default = True
                for field in value.field_tuples:
                    if not isinstance(field, tuple) or len(field) < 3:
                        # no default specified
                        can_make_default = False
                if can_make_default:
                    pipeline = value(f"{value.type_name}_default")
                    self.add_pipeline_to_ref_names(
                        module_str, value.type_name, pipeline
                    )

        # return the piece of the module_str that wasn't the module
        return remainder

    def add_pipeline_to_ref_names(self, module_str: str, attr_name: str, pipeline):
        """Add the pipeline to the ref names dictionary under all logical names."""
        module_pieces = module_str.split(".")

        # TODO: handle if name already exists
        for i in range(len(module_pieces) + 1):
            if i == 0:
                self.pipeline_ref_names[attr_name] = pipeline
                self.pipeline_ref_names[pipeline.name] = pipeline
                continue
            building_module_str = ".".join(module_pieces[-i:])
            self.pipeline_ref_names[f"{building_module_str}.{attr_name}"] = pipeline
            self.pipeline_ref_names[f"{building_module_str}.{pipeline.name}"] = pipeline
            self.logger.debug(
                f"Adding pipeline {pipeline.name} at {building_module_str}.{pipeline.name}"
            )

    def divide_reference_parts(self, ref_str: str) -> dict[str, str]:
        parts = {"module": None, "pipeline": None, "artifact_filter": None}

        # TODO: check for  historical pipeline name

        for module_name in self.imported_module_names:
            if ref_str.startswith(module_name):
                parts["module"] = module_name
                ref_str = ref_str[len(module_name) :]
                if ref_str.startswith("."):
                    ref_str = ref_str[1:]
                break

        for name in self.pipeline_ref_names:
            if ref_str.startswith(name) and (
                len(ref_str) == len(name) or ref_str[len(name) : len(name) + 1] == "."
            ):
                parts["pipeline"] = self.pipeline_ref_names[name].name
                ref_str = ref_str[len(name) :]
                if ref_str.startswith("."):
                    ref_str = ref_str[1:]
                break
        if parts["pipeline"] is None:
            parts["pipeline"] = ref_str
            return parts

        if ref_str == "":
            parts["artifact_filter"] = None
        else:
            parts["artifact_filter"] = ref_str
        return parts

    def quietly_import_module(self, module_str: str):
        """Doesn't raise an error if the module in module_str isn't found.
        (All other exceptions will still raise)"""
        module = None
        try:
            module = importlib.import_module(module_str)
        except ModuleNotFoundError as e:
            if not module_str.endswith(e.name):
                raise
            pass
        return module

    # def find_pipelines_from_file(self, file_path: str):
    #     with self:
    #         importlib.import_module(file_path)

    # def check_for_existing_run_in_db(self, target_artifact):
    #     pass

    def search_for_db_artifact(self, artifact):
        with self.db_connection() as db:
            results = db.sql(
                "SELECT * FROM cf_artifact WHERE name = $artifact_name AND hash = $artifact_hash",
                params=dict(
                    artifact_name=artifact.name,
                    artifact_hash=artifact.compute_hash()[0],
                ),
            ).df()
        return results

    def search_for_artifact_generating_run(self, artifact_id):
        with self.db_connection() as db:
            results = (
                db.sql(
                    """
                SELECT cf_run.* FROM cf_run
                JOIN cf_artifact ON cf_run.id = cf_artifact.run_id
                WHERE cf_artifact.id = $artifact_id
                """,
                    params=dict(artifact_id=artifact_id),
                )
                .df()
                .iloc[0]
            )
        return results

    def ensure_sys_path(self):
        if self._sys_paths_added:
            return

        # TODO: find root
        if self.project_root is None:
            search_depth = 3
            prefix = "./"
            while (
                not os.path.exists(f"{prefix}{CONFIGURATION_FILE}") and search_depth > 0
            ):
                prefix += "../"
                search_depth -= 1
            if os.path.exists(f"{prefix}{CONFIGURATION_FILE}"):
                self.project_root = str(Path(prefix).resolve())

        if self.project_root is not None:
            sys.path.append(self.project_root)
        sys.path.append(os.getcwd())
        self._sys_paths_added = True

    def ensure_dir_paths(self):
        database_dir = Path(self.database_path).parent
        database_dir.mkdir(parents=True, exist_ok=True)
        Path(self.cache_path).mkdir(parents=True, exist_ok=True)
        Path(self.reports_path).mkdir(parents=True, exist_ok=True)

    def ensure_store_tables(self):
        with self.db_connection() as db:
            cf.db_tables.ensure_tables(db)

    # def get_current_stage_artifact_path(self, artifact_index = 0):
    #     artifact = self.current_stage.outputs[artifact_index]
    #     if artifact.cacher is None:
    #         return None
    #     return artifact.cacher.get_path(dry=True)

    def load_artifact_metadata_by_id(
        self, db_id: UUID, artifact: "cf.artifact.Artifact"
    ) -> bool:
        # returns False if didn't find
        pass

    # TODO: unclear if these should be associated with an pipeline run instead
    # of an pipeline or manager class
    def get_str_timestamp(self, pipeline) -> str:
        """Convert the manager's run timestamp into a string representation."""
        return pipeline.start_timestamp.strftime(TIMESTAMP_FORMAT)

    def get_reference_name(self, pipeline) -> str:
        """Get the reference name of this run in the pipeline registry.

        The format for this name is ``[pipeline_name]_[run_number]_[timestamp]``."""
        return (
            f"{pipeline.name}_{pipeline.run_number}_{self.get_str_timestamp(pipeline)}"
        )

    def get_next_pipeline_run_number(self, pipeline) -> int:
        with self.db_connection() as db:
            num = db.sql(
                "SELECT MAX(run_number) FROM cf_run WHERE pipeline_name = $pipelinename",
                params=dict(pipelinename=pipeline.name),
            ).fetchone()[0]
            if num is None:
                num = 0
            return num + 1

    def get_artifact_obj_repr(self, artifact) -> str:
        if artifact.obj is None:
            return ""
        display_str = ""
        if type(artifact.obj) in self.repr_functions:
            display_str = self.repr_functions[type(artifact.obj)](artifact.obj)
        else:
            display_str = repr(artifact.obj)
        if len(display_str) >= 100:
            return display_str[100]
        return display_str

    def record_artifact(self, artifact):
        if not self.currently_recording:
            return

        artifact_id = uuid4()
        gen_time = datetime.now()

        artifact.db_id = artifact_id
        artifact.generated_time = gen_time

        run_id = artifact.context.db_id if artifact.context is not None else None

        if artifact == self.current_pipeline_run_target:
            self.record_pipeline_run_target(self.current_pipeline_run, artifact)

        cacher_type = None
        cacher_module = None
        cacher_params = None
        if artifact.cacher is not None:
            cacher_type = artifact.cacher.__class__.__name__
            cacher_module = artifact.cacher.__class__.__module__
            cacher_params = artifact.cacher.get_params()

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_artifact (
                        id,
                        stage_id,
                        run_id,
                        name,
                        hash,
                        generated_time,
                        artifact_type,
                        cacher_type,
                        cacher_module,
                        cacher_params,
                        repr,
                        is_list
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    artifact_id,
                    artifact.compute.db_id if artifact.compute is not None else None,
                    run_id,
                    artifact.name,
                    artifact.compute_hash()[0],
                    gen_time,
                    artifact.__class__.__name__,
                    cacher_type,
                    cacher_module,
                    cacher_params,
                    self.get_artifact_obj_repr(artifact),
                    isinstance(artifact, cf.artifact.ArtifactList),
                ],
            )

    def record_stage_artifact_input(self, stage, artifact, arg_index, arg_name):
        if not self.currently_recording:
            return

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_stage_input (
                        stage_id,
                        artifact_id,
                        arg_index,
                        arg_name
                    )
                    VALUES (?, ?, ?, ?)
                """,
                [stage.db_id, artifact.db_id, arg_index, arg_name],
            )

    def record_stage_dependency(self, stage, dependency_stage):
        if not self.currently_recording:
            return

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_stage_input (
                        stage_id,
                        stage_dependency_id
                    )
                    VALUES (?, ?)
                """,
                [stage.db_id, dependency_stage.db_id],
            )

    def record_stage(self, stage):
        if not self.currently_recording:
            return

        self.logger.debug(f"Recording stage {stage.contextualized_name}")

        stage_id = uuid4()
        func_name = stage.name
        hash, hash_debug = stage.compute_hash()
        stage.db_id = stage_id

        self.logger.debug(f"(id: {stage.db_id})")

        run_id = stage.context.db_id if stage.context is not None else None

        func_module = stage.function.__module__

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_stage (
                        id,
                        run_id,
                        func_name,
                        func_module,
                        hash,
                        hash_details
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                [stage_id, run_id, func_name, func_module, hash, hash_debug],
            )

    def record_stage_start(self, stage):
        if not self.currently_recording:
            return

        start_time = datetime.now()
        with self.db_connection() as db:
            db.sql(
                "UPDATE cf_stage SET start_time = $starttime, WHERE ID = $id",
                params=dict(starttime=start_time, id=stage.db_id),
            )

    def record_stage_completion(self, stage):
        if not self.currently_recording:
            return

        end_time = datetime.now()
        with self.db_connection() as db:
            db.sql(
                "UPDATE cf_stage SET end_time = $endtime, WHERE ID = $id",
                params=dict(endtime=end_time, id=stage.db_id),
            )

    # TODO: is it worth having an pipeline_run object?
    # TODO: rename to record_pipeline_run
    def record_pipeline_run(self, pipeline):
        if not self.currently_recording:
            return

        pipeline_id = uuid4()  # TODO: should base on reference name?
        run_num = self.get_next_pipeline_run_number(pipeline)

        pipeline.db_id = pipeline_id
        pipeline.run_number = run_num
        pipeline.start_timestamp = datetime.now()
        pipeline.reference = self.get_reference_name(pipeline)

        hash, _ = pipeline.compute_hash()

        cleaned_parameters = pipeline.parameters
        cleaned_parameters_str = json.dumps(cleaned_parameters, default=repr)
        cleaned_parameters = json.loads(cleaned_parameters_str)

        # for parameter in pipeline.parameters:
        #     if isinstance(pipeline.parameter, cf.pipeline.Experiment):
        #         pipeline.parameters[parameter] =

        with self.db_connection() as db:
            db.execute(
                """
                    INSERT INTO cf_run (
                        id,
                        reference,
                        pipeline_class,
                        pipeline_name,
                        run_number,
                        start_time,
                        hash,
                        params
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    pipeline_id,
                    pipeline.reference,
                    pipeline.__class__.__name__,
                    pipeline.name,
                    pipeline.run_number,
                    pipeline.start_timestamp,
                    hash,
                    cleaned_parameters,
                ],
            )

    def record_pipeline_run_target(self, pipeline, target):
        if not self.currently_recording:
            return

        with self.db_connection() as db:
            db.sql(
                """UPDATE cf_run SET target_id = $target_id, WHERE ID = $id""",
                params=dict(target_id=target.db_id, id=pipeline.db_id),
            )

    def record_pipeline_run_completion(self, pipeline):
        if not self.currently_recording:
            return

        pipeline.end_timestamp = datetime.now()
        with self.db_connection() as db:
            db.sql(
                """UPDATE cf_run SET end_time = $endtime, succeeded = true, WHERE ID = $id""",
                params=dict(endtime=pipeline.end_timestamp, id=pipeline.db_id),
            )

    def record_pipeline_failure(self, exception, stack):
        if self.current_pipeline_run_target is None:
            return

        pipeline = self.current_pipeline_run_target
        pipeline.end_timestamp = datetime.now()
        exception_text = f"{type(exception).__name__}: {exception}"
        with self.db_connection() as db:
            db.sql(
                """UPDATE cf_run SET
                    end_time = $endtime,
                    succeeded = false,
                    exception = $exception,
                    exception_stack = $exception_stack,
                WHERE ID = $id""",
                params=dict(
                    endtime=pipeline.end_timestamp,
                    id=pipeline.db_id,
                    exception=exception_text,
                    exception_stack=stack,
                ),
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
        """The CLI sets this."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        rich_log_formatter = logging.Formatter("%(prefix)s%(message)s")
        console_handler = RichHandler(
            console=get_console(),
            show_time=True,
            show_level=True,
            show_path=True,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            log_time_format="%X",
            keywords=["-----", "=====", ".....", "#####"],
        )

        console_handler.setFormatter(rich_log_formatter)
        root_logger.addHandler(console_handler)

        cf.utils.set_logging_prefix("")

    def init_cf_logging(self):
        cf_logger = logging.getLogger("curifactory")
        # cf_logger.setLevel(logging.INFO)
        # cf_logger.setLevel(logging.DEBUG)
        # NOTE: see https://docs.python.org/3/howto/logging.html#library-config
        # probably don't add a handler by default?
        # cf_logger.addHandler(logging.StreamHandler())
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

        config = {}

        if os.path.exists(f"{prefix}{CONFIGURATION_FILE}"):
            with open(f"{prefix}{CONFIGURATION_FILE}") as infile:
                config = json.load(infile)

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
