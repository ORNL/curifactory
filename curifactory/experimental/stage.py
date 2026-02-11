import copy
import hashlib
import inspect
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Union
from uuid import UUID

import pandas as pd
import psutil

# NOTE: resource only exists on unix systems
if os.name != "nt":
    import resource

import curifactory.experimental as cf


class FunctionStub:
    def __init__(self, name, func_module=None):
        self.name = name
        self.func_module = func_module

    def __call__(self, **kwargs):
        raise

    def __getattr__(self, attr_name):
        if attr_name == "__name__":
            return self.name


class _StageContext(threading.local):
    def __init__(self):
        self.current_stage_dependencies: list[Stage] = []

    @property
    def stage_dependencies(self):
        return self.current_stage_dependencies


STAGE_CONTEXT = _StageContext()


class OutputArtifactPathResolve:
    """Used for getting the path of an _output_ artifact as an _input_ to the stage."""

    def __init__(self, output_artifact_index):
        self.output_artifact_index = output_artifact_index

    def resolve(self, stage):
        # cf.get_manager().get_current_stage_artifact_path(self.output_artifact_index)
        if isinstance(stage.outputs, cf.artifact.Artifact):
            artifact = stage.outputs
        else:
            artifact = stage.outputs[self.output_artifact_index]
        if artifact.cacher is None:
            return None
        return artifact.cacher.get_path(dry=True)


class ConfigResolve:
    """Check global config at runtime for specified key, or use specified default if not found.

    This can either be used in a stage def or cacher.
    """

    def __init__(self, config_key_name: str, default: Any = None):
        self.config_key_name = config_key_name
        self.default = default

    def resolve(self):
        global_config = cf.global_config()
        if self.config_key_name in global_config:
            return global_config[self.config_key_name]
        return self.default


@dataclass
class Stage:
    """Essentially a fancy "partial" that assigns outputs to instance
    attributes typed as Artifacts."""

    # TODO: we probably also need to track larger context = pass in the
    # pipeline to the stage

    function: callable
    args: list
    kwargs: dict

    outputs: Union[list["cf.artifact.Artifact"], "cf.artifact.Artifact"]
    hashing_functions: dict[str, callable] = None
    pass_self: bool = False

    # TODO: (6/28/2024) have a bool for whether this has instance has run yet or
    # not (might be necessary for a PreStage context manager)

    db_id: UUID = None

    dependencies: list["Stage"] = field(default_factory=list)
    """Explicit stage dependencies that don't have outputs used in this stage
    but are still required to run first. (Either set explicitly or use
    within a context manager)"""

    computed: bool = False
    """Mostly only used to help ensure output-less dependencies don't run more
    than once."""

    from_ref: bool = False
    """Indicates that it was populate by reference rather than by code - underlying
    function may not exist or be accessible if True"""

    hash_str: str = None
    hash_debug: dict[str, dict[str, Any]] = None

    def __post_init__(self):
        # create a dictionary with the names of all the function arguments and
        # where they can be found index-wise
        # TODO: this isn't going to work if a stage is loaded from db and no
        # underlying function, may need to save this somewhere.
        # self._parameters = {}
        """This contains the signature inspection parameter info. Retaining this because
        repeated calls to inspect (e.g. in compute_hash) add up processing time quite a bit.
        """
        self.parameter_kinds = {}
        self.parameter_positions = {}
        self.parameter_defaults = {}

        if not isinstance(self.function, FunctionStub):
            parameters = inspect.signature(self.function).parameters
            for i, key in enumerate(parameters.keys()):
                # self._parameters[key] = {"default": parameters[key].default, "kind": parameters[key].kind}
                self.parameter_kinds[key] = parameters[key].kind
                self.parameter_positions[key] = i
                if parameters[key].default != inspect.Parameter.empty:
                    self.parameter_defaults[key] = parameters[key].default
                else:
                    self.parameter_defaults[key] = None

        artifacts = []
        if not isinstance(self.outputs, list):
            # turn it into a list for now just for consistent handling, will be
            # collapsed later
            self.outputs = [self.outputs]
        for output in self.outputs:
            # TODO: after new artifact created below, probably need to remove
            # output from its context's artifact manager? (since it was likely
            # just the stage decorator artifact)

            # TODO: throw error if output name isn't a valid python var name

            # setattr(self, name, field(default=None))
            # TODO: there should probably be an artifact copy function
            art = cf.artifact.Artifact()
            output.name = self.resolve_template_string(output.name)
            art.name = output.name
            # NOTE: remember that objects defined in the decorator are
            # singletons, so the cacher needs to be "created again" to ensure
            # that every instance of the stage/artifact has a _different_ cacher
            # (otherwise all cacher(s) will refer to the same artifact)
            art.cacher = copy.deepcopy(output.cacher)

            art.compute = self
            if output.name is not None:
                setattr(self, output.name, art)
            artifacts.append(art)
        self.outputs = artifacts

        # unclear if this is the way to go to handle more tuple like returns
        # from pipeline definitions when assigning stage outputs
        if len(self.outputs) == 1:
            self.outputs = self.outputs[0]

        # self._assign_dependents()
        self.context = self._find_context()
        # TODO: previous context names similar to artifact?

        # figure out any dependencies from context managers
        if len(STAGE_CONTEXT.stage_dependencies) > 0:
            for dependency in STAGE_CONTEXT.stage_dependencies:
                self.dependencies.append(dependency)

        self.map_status: int = None

        self.reportables_list: list[cf.reporting.Reportable] = []
        self._reportables: cf.artifact.StageReportables = None
        self._reportables_ready: bool = False

    def _find_context(self) -> "cf.pipeline.Pipeline":
        if len(cf.get_manager()._pipeline_defining_stack) > 0:
            # self.context = cf.get_manager()._pipeline_defining_stack[-1]
            return cf.get_manager()._pipeline_defining_stack[-1]
        return None

        # TODO: check if context is none first?
        # for frame in inspect.stack():
        #     if "self" in frame.frame.f_locals.keys() and isinstance(
        #         frame.frame.f_locals["self"], cf.experiment.Experiment
        #     ):
        #         # print("FOUND THE EXPERIMENT")
        #         return frame.frame.f_locals["self"]
        # return None

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # if name == "args" or name == "kwargs":
        #     self._assign_dependents()

    def __enter__(self):
        STAGE_CONTEXT.stage_dependencies.append(self)

    def __exit__(self, exc_type, exc_value, traceback):
        STAGE_CONTEXT.stage_dependencies.remove(self)

    @property
    def contextualized_name(self):
        if self.context is not None:
            return f"{self.context.name}.{self.name}"
        return self.name

    @property
    def reportables(self):
        if self._reportables is None:
            self._reportables = cf.artifact.StageReportables()
            self._reportables.compute = self
            self._reportables.obj = self.reportables_list
        if not self._reportables_ready:
            if self._reportables.cacher.check(silent=True):
                self._reportables.obj = self._reportables.cacher.load()
                self.reportables_list = self._reportables.obj
                self._reportables_ready = True
        return self._reportables

    # def _assign_dependents(self):
    #     """Go through args and kwargs and for any artifacts, add this stage
    #     to their dependents."""
    #     # TODO: we obv don't want cross experiment/context dependents, so
    #     # maybe we error if the input is from different context? Or maybe
    #     # this is where we handle automatically creating a copy instead. (No
    #     # actually I think that should get handled in replace in artifact?) Or
    #     # maybe both.
    #     for arg in self._combined_args():
    #         if isinstance(arg, artifact.Artifact) and self not in arg.dependents:
    #             arg.dependents.append(self)

    # def define(self, *args, **kwargs):
    #     # TODO: only necessary for modeltest2, prob not the best name
    #     self.args = args
    #     self.kwargs = kwargs

    def _inner_copy(
        self,
        # TODO: types below are wrong
        building_stages: dict["cf.stage.Stage", "cf.stage.Stage"] = None,
        building_artifacts: dict["cf.artifact.Artifact", "cf.artifact.Artifact"] = None,
    ) -> tuple["Stage", bool]:
        """Returns the created (or prev) stage and whether it was indeed created or not."""
        if building_stages is None:
            building_stages = {}
        if building_artifacts is None:
            building_artifacts = {}

        if id(self) in building_stages.keys():
            return building_stages[id(self)]  # , False

        copied_args = []
        for arg in self.args:
            if isinstance(arg, cf.artifact.Artifact):
                copied_args.append(arg._inner_copy(building_stages, building_artifacts))
            else:
                copied_args.append(copy.deepcopy(arg))
        copied_kwargs = {}
        for kw in self.kwargs:
            arg = self.kwargs[kw]
            if isinstance(arg, cf.artifact.Artifact):
                copied_kwargs[kw] = arg._inner_copy(building_stages, building_artifacts)
            else:
                copied_kwargs[kw] = copy.deepcopy(arg)

        # TODO: shouldn't outputs be copied as well rather than just inputs?
        # Otherwise risk problem of "unused" outputs not getting copied
        # correctly

        new_stage = Stage(
            self.function,
            copied_args,
            copied_kwargs,
            self.outputs,
            self.hashing_functions,
            self.pass_self,
        )
        building_stages[id(self)] = new_stage

        # copy reportables artifact if relevant
        if len(self.reportables_list) > 0:
            if self._reportables is not None:
                new_stage._reportables = self._reportables._inner_copy(
                    building_stages, building_artifacts
                )
                # TODO: set reportables_loaded as well?

        # handle copying any stage dependencies
        for dependency in self.dependencies:
            if id(dependency) not in building_stages:
                new_dependency = dependency._inner_copy(
                    building_stages, building_artifacts
                )
                building_stages[id(dependency)] = new_dependency

            new_stage.dependencies.append(building_stages[id(dependency)])
        return new_stage  # , True

    def copy(self):
        return self._inner_copy(None, None)

    @staticmethod
    def load_from_uuid(
        uuid,
        building_stages: dict = None,
        building_artifacts: dict = None,
        prepopulated_stage=None,
    ):
        """Recurisvely load all input artifacts and their dependencies and then return the stage they feed into. Note that function stubs are used by default."""
        if building_stages is None:
            building_stages = {}
        if building_artifacts is None:
            building_artifacts = {}

        if uuid in building_stages:
            return building_stages[uuid]

        with cf.get_manager().db_connection() as db:
            stage_row = (
                db.sql(f"select * from cf_stage where id = '{uuid}'").df().iloc[0]
            )
            stage_input_rows = db.sql(
                f"select * from cf_stage_input where stage_id = '{uuid}'"
            ).df()

        if prepopulated_stage is not None:
            stage = prepopulated_stage
        else:
            stage = Stage(FunctionStub(stage_row.func_name), [], {}, outputs=[])
            stage.from_ref = True
            stage.hash_str = stage_row.hash
            stage.hash_debug = stage_row.hash_details
        stage.db_id = uuid

        building_stages[uuid] = stage

        stage_inputs = []
        for index, row in stage_input_rows.iterrows():
            if not pd.isna(row["artifact_id"]):
                stage_inputs.append(
                    cf.artifact.Artifact.load_from_uuid(
                        row["artifact_id"], building_stages, building_artifacts
                    )
                )
            elif not pd.isna(row["stage_dependency_id"]):
                stage.dependencies.append(
                    Stage.load_from_uuid(
                        row["stage_dependency_id"], building_stages, building_artifacts
                    )
                )

        stage.args = stage_inputs
        return stage

    def compute_hash(self) -> tuple[str, dict[str, dict[str, Any]]]:
        if self.from_ref:
            return self.hash_str, self.hash_debug

        parameter_names = list(self.parameter_kinds.keys())

        # iterate through each parameter and get its hash value
        debug = {}
        hash_values = {}
        for param_index, param_name in enumerate(parameter_names):
            # if self.pass_self and param_index == 0:
            #     continue
            # if self.pass_self:
            #     param_index -= 1
            parameter_value = self.get_parameter_value(param_index, param_name)
            # TODO: get_parameter_value actually won't handle self since it's
            # not explicitly in the _user_passed_ args.
            if isinstance(parameter_value, Stage) or param_name == "self":
                # ignore if self is passed
                # NOTE: I'm doing this instead of an explicit pass_self check in
                # case other tools externally manipulate stages and hide self
                # pass.
                continue

            # check for a *args type parameter
            if self.parameter_kinds[param_name] == inspect.Parameter.VAR_POSITIONAL:
                inner_parameters = self.args[param_index:]
                hash_debug = []
                hash_value = []
                for param in inner_parameters:
                    inner_debug, inner_value = self.hash_parameter(param_name, param)
                    hash_debug.append(inner_debug)
                    hash_value.append(inner_value)
            else:
                hash_debug, hash_value = self.hash_parameter(
                    param_name, parameter_value
                )
            debug[param_name] = {"object": hash_debug, "hash_value": hash_value}
            hash_values[param_name] = hash_value

        # add any stage dependencies
        for stage_dependency in self.dependencies:
            hash_debug, hash_value = self.hash_parameter(
                stage_dependency.name, stage_dependency
            )
            debug[stage_dependency.name] = hash_debug
            hash_values[stage_dependency.name] = hash_value

        hash_total = 0
        for key, value in hash_values.items():
            if value is None:
                continue

            hash_hex = hashlib.md5(f"{key}{value}".encode()).hexdigest()
            hash_total += int(hash_hex, 16)

        hash_str = f"{hash_total:x}"
        self.hash_str = hash_str
        self.hash_debug = debug
        return hash_str, debug

    def get_parameter_value(self, param_index, param_name):
        if param_index < len(self.args):
            return self.args[param_index]
        if param_name in self.kwargs:
            return self.kwargs[param_name]
        # otherwise get the default
        return self.parameter_defaults[param_name]

    def hash_parameter(self, param_name, param_value) -> tuple[str, any]:
        # 1. see if user has specified how to handle the hash representation
        if self.hashing_functions is not None and param_name in self.hashing_functions:
            # if they set it to None, ignore it
            if self.hashing_functions[param_name] is None:
                return ("SKIPPED: set to None in hash_functions", None)
            # otherwise, call the user provided function
            return (
                f"hashing_functions['{param_name}'](param_value)",
                self.hashing_functions[param_name](param_value),
            )

        # 2. if the value itself is None, nothing to hash, so don't include it.
        if param_value is None:
            return ("SKIPPED: value is None", None)

        # 3. if the parameter is an artifact, use its hash
        if isinstance(param_value, cf.Artifact):
            # TODO: artifact needs to track the hash_debug and re-include it here.
            param_value.compute_hash()
            return (
                # f"artifact {param_value.name}.hash - '{param_value.hash_debug}'",
                {"artifact": param_value.name, "hash": param_value.hash_debug},
                param_value.hash_str,
            )

        # 4. if the parameter is a stage (e.g. a stage dependency) use its hash
        if isinstance(param_value, Stage):
            hash_str, hash_debug = param_value.compute_hash()
            # return (f"stage {param_value.name}.hash - '{hash_debug}'", hash_str)
            return ({"stage": param_value.name, "hash": hash_debug}, hash_str)

        # 5. use the function name if it's a callable, rather than a pointer address
        if isinstance(param_value, Callable):
            return (f"{param_name}.__qualname__", param_value.__qualname__)

        # 6. otherwise just use the default representation
        return (f"repr({param_name})", repr(param_value))

    def resolve_template_string(self, str_to_format: str) -> str:
        """
        * {hash}
        * {stage_name}
        * {[PARAMETER_NAME]}
        * {[PARAMETER_NAME].name} - the name of the PARAMETER artifact (if it is in fact an artifact)
        """
        format_dict = cf.utils.FailsafeDict(
            hash=self.compute_hash(), stage_name=self.name
        )
        # for i in range(len(self.parameter_positions)):
        #     arg = None
        #     if i >= len(self.args):
        #         # find the kwarg name
        #         for kwarg, index in self.parameter_positions.items():
        #             if index == i:
        #                 if kwarg in self.kwargs:
        #                     arg = self.kwargs[kwarg]
        #                 else:
        #                     # TODO: need to also look at handling default parameter values
        #                     arg = None
        #     else:
        #         arg = self.args[i]
        #     format_dict[f"arg_{i}"] = str(arg)
        #
        for parameter in self.parameter_positions:
            val = self.get_parameter_value_by_name(parameter)
            format_dict[parameter] = str(val)

            if isinstance(val, cf.artifact.Artifact):
                format_dict[f"{parameter}.name"] = val.name

        return str_to_format.format(**format_dict)
        # return Template(str_to_format).safe_substitute(**format_dict)

    def get_parameter_value_by_name(self, parameter_name: str):
        if parameter_name in self.kwargs:
            return self.kwargs[parameter_name]
        i = self.parameter_positions[parameter_name]
        if i < len(self.args):
            return self.args[i]
        return self.parameter_defaults[parameter_name]

    # def get_parameter_value_by_index(self, index: int):
    #     pass

    def _combined_args(self) -> list:
        """Put the kwargs into a list, this is mostly just to make it easier to scan
        all inputs for artifacts."""
        if hasattr(self, "kwargs"):
            return list(self.args) + list(self.kwargs.values())
        else:
            return list(self.args)

    def _artifact_tree(self) -> dict[str, dict]:
        """Recursive all the way down."""
        tree = {}
        # TODO: if two artifacts have the same name in an artifact list, they
        # overwrite eachother in the tree dict. Will need to handle auto array
        # logic for ArtifactLists? Or make everything be a list of dicts instead
        for arg in self.args:
            if isinstance(arg, cf.artifact.Artifact):
                tree[arg.name] = arg.compute._artifact_tree()
        for kwarg in self.kwargs:
            if isinstance(self.kwargs[kwarg], cf.artifact.Artifact):
                tree[arg.name] = arg.compute._artifact_tree()

        if len(tree.keys()) == 0:
            return None
        return tree

    def visualize(self, g=None, **kwargs):
        if g is None:
            g = cf.utils.init_graphviz_graph()

        self._node(g)

        for dependency in self.artifacts:
            # don't add duplicate edges (can happen when visualizing from a
            # filter)
            if (str(dependency.internal_id), str(id(self))) not in g._edges:
                self._edge_from_artifact(g, dependency, **kwargs)
                g._edges.append((str(dependency.internal_id), str(id(self))))
            g = dependency.visualize(g, **kwargs)

        # add arrows directly from any explicit previous stage dependencies to
        # this one
        for stage in self.dependencies:
            if (str(id(stage)), str(id(self))) not in g._edges:
                g.edge(str(id(stage)), str(id(self)))
                g._edges.append((str(id(stage)), str(id(self))))
            g = stage.visualize(g, **kwargs)

        return g

    def _edge_from_artifact(self, g, artifact, **kwargs):
        if "color" in kwargs and kwargs["color"] == "cache":
            cache_status = artifact.cacher is not None and artifact.cacher.check(
                silent=True
            )
            if cache_status:
                color = "#33AA33"
            else:
                color = "#AA3333"
            if artifact.cacher is None:
                color = "#555555"
            g.edge(
                str(artifact.internal_id),
                str(id(self)),
                color=color,
            )
        else:
            g.edge(str(artifact.internal_id), str(id(self)))

    def _node(self, dot):
        dot.node(
            name=str(id(self)),
            label=self.name,
            fontsize="8.0",
            height=".25",
            fillcolor="#BBBBBB",
            style="filled",
        )

    def _stage_list():
        # TODO
        pass

    def reset_map(self):
        self.map_status = None
        if isinstance(self.outputs, (list, cf.artifact.ArtifactList)):
            for artifact in self.outputs:
                artifact.map_status = None
        else:
            self.outputs.map_status = None

        for artifact in self.artifacts:
            artifact.reset_map()

        for dependency in self.dependencies:
            dependency.reset_map()

    def get_output_list(self):
        """Make it easier to act on outputs without always having to first chekc if it's a list or not."""
        # if isinstance(self.outputs, (list, cf.artifact.ArtifactList)):
        if isinstance(self.outputs, list):
            return self.outputs
        return [self.outputs]

    def map(self, mapped: dict = None, need: bool = True, source=None):
        if mapped is None:
            self.reset_map()
            mapped = {
                "artifacts": [],
                "stages": [],
                "map": {},
            }
        if source is not None:
            map_name = f"{source.name} -> {self.name}"
        else:
            map_name = f"-> {self.name}"
        if self.name not in mapped["map"]:
            mapped["map"][self.name] = {}
        if map_name not in mapped["map"][self.name]:
            mapped["map"][self.name][map_name] = []

        if need:
            # handle differently if this is a stage dependency?
            if isinstance(source, Stage) and len(self.get_output_list()) > 0:
                # assume the artifacts will take care of this
                for artifact in self.get_output_list():
                    mapped = artifact.map(mapped, need=True, source=self)
                need = False
            else:
                self.map_status = cf.COMPUTE
                mapped["map"][self.name][map_name].append(cf.COMPUTE)

                for artifact in self.get_output_list():
                    if artifact != source:
                        mapped = artifact.map(mapped, need=True, source=self)
                        # override status
                        if artifact.map_status != cf.OVERWRITE:
                            artifact.map_status = cf.COMPUTE
                            mapped["map"][artifact.name][
                                f"{self.name} -> {artifact.name}"
                            ][-1] = cf.COMPUTE

        if self not in mapped["stages"]:
            mapped["stages"].insert(0, self)

            if not need:
                self.map_status = cf.SKIP
                mapped["map"][self.name][map_name].append(cf.SKIP)
                # this is only in here in the insertion part because needing
                # compute takes precedence over not (if we'd already determined
                # elsewhere this needs to run, we don't override that)
                for artifact in self.get_output_list():
                    if artifact != source:
                        mapped = artifact.map(mapped, need=False, source=self)
        else:
            # we want stages list to correspond loosely to execution order, so
            # if we need a stage earlier on, make sure to move it back to front.
            mapped["stages"].insert(
                0, mapped["stages"].pop(mapped["stages"].index(self))
            )

        for artifact in self.artifacts:
            mapped = artifact.map(mapped, need, source=self)

        for dependency in self.dependencies:
            mapped = dependency.map(mapped, need, source=self)

        return mapped

    @property
    def name(self):
        return self.function.__name__

    @property
    def artifacts(self):
        artifact_list = []
        for arg in self._combined_args():
            if isinstance(arg, cf.artifact.Artifact):
                artifact_list.append(arg)
        return cf.artifact.ArtifactFilter(artifact_list)  # TODO: need a filter_string?

    def resolve_arg(
        self,
        record_resolution: bool = False,
        arg_index: int = None,
        arg_name: str = None,
    ):
        obj = None
        arg = None

        if arg_index is not None:
            arg = self._combined_args()[arg_index]
        elif arg_name is not None:
            arg = self.kwargs[arg_name]

        if isinstance(arg, Stage):
            cf.get_manager().logger.warn(
                f"WARNING: Stage argument passed into {self.name}, is there a missing .outputs?"
            )

        if isinstance(arg, cf.artifact.Artifact):
            if cf.get_manager().error_state:
                return None
            obj = arg.get()
            if cf.get_manager().error_state:
                return None
            if record_resolution:
                cf.get_manager().record_stage_artifact_input(
                    self, arg, arg_index, arg_name
                )
        elif isinstance(arg, (OutputArtifactPathResolve, ConfigResolve)):
            obj = arg.resolve(self)
        else:
            obj = arg

        return obj

    # TODO: this really maybe only makes sense to be called from within the
    # stage __call__...
    def resolve_args(self, record_resolution: bool = False) -> tuple[list, dict]:
        """Handle any artifacts passed in as arguments."""
        passed_args = []
        passed_kwargs = {}

        for i, arg in enumerate(self.args):
            passed_args.append(self.resolve_arg(record_resolution, arg_index=i))
        for kwarg in self.kwargs:
            passed_kwargs[kwarg] = self.resolve_arg(record_resolution, arg_name=kwarg)

        # manager = cf.get_manager()
        # compute any inputs
        # for arg in self.args:
        #     # if a stage was passed in instead of an artifact, quite possible
        #     # user forgot a .outputs, so warn
        #     if isinstance(arg, Stage):
        #         print(
        #             f"WARNING: Stage argument passed into {self.name}, is there a missing .outputs?"
        #         )
        #
        #     if isinstance(arg, cf.artifact.Artifact):
        #         # if not arg.computed:
        #         #     arg.compute()
        #         obj = arg.get()
        #         passed_args.append(obj)
        #         if record_resolution:
        #             manager.record_stage_artifact_input(self, arg)
        #         # passed_args.append(arg.obj)
        #     elif isinstance(arg, OutputArtifactPathResolve):
        #         passed_args.append(arg.resolve(self))
        #     else:
        #         passed_args.append(arg)
        # for kwarg in self.kwargs:
        #     if isinstance(self.kwargs[kwarg], cf.artifact.Artifact):
        #         # if not self.kwargs[kwarg].computed:
        #         #     self.kwargs[kwarg].compute()
        #         obj = self.kwargs[kwarg].get()
        #         passed_kwargs[kwarg] = obj
        #         if record_resolution:
        #             manager.record_stage_artifact_input(self, self.kwargs[kwarg])
        #         # passed_kwargs[kwarg] = self.kwargs[kwarg].obj
        #     elif isinstance(self.kwargs[kwarg], OutputArtifactPathResolve):
        #         passed_args.append(self.kwargs[kwarg].resolve(self))
        #     else:
        #         passed_kwargs[kwarg] = self.kwargs[kwarg]
        #
        if self.pass_self:
            passed_args.insert(0, self)

        return passed_args, passed_kwargs

    def __call__(self):  # noqa: C901
        try:
            manager = cf.get_manager()

            # if we have no active run but a stage needs to execute, that means we
            # need to start an implicit run
            implicit_run = False
            if manager.current_pipeline_run is None and self.context is not None:
                implicit_run = True
                self.context._implicit_run()

            # TODO: all these cf.get_manager.error_state is a mess, clean up?

            # make sure any dependencies have run. # TODO: not sure on order of this
            for dependency in self.dependencies:
                manager.logger.info(
                    f"Ensuring {self.name} stage dependency of {dependency.name}"
                )
                if isinstance(dependency.outputs, list):
                    for output in dependency.outputs:
                        output.get()
                        if cf.get_manager().error_state:
                            return None
                elif isinstance(dependency.outputs, cf.artifact.Artifact):
                    dependency.outputs.get()
                    if cf.get_manager().error_state:
                        return None
                elif not dependency.computed:
                    dependency()
                    if cf.get_manager().error_state:
                        return None

            manager.record_stage(self)

            for dependency in self.dependencies:
                # NOTE: have to record these here rather than when they're run,
                # otherwise we don't have a db id yet
                manager.record_stage_dependency(self, dependency)

            manager.logger.info(
                f"..... Beginning resolution for stage {self.contextualized_name} ....."
            )
            passed_args, passed_kwargs = self.resolve_args(record_resolution=True)
            if cf.get_manager().error_state:
                return None

            manager.logger.info(
                f"===== Executing stage {self.contextualized_name} ====="
            )
            manager.record_stage_start(self)
            manager.current_stage = self

            pre_mem_usage = psutil.Process().memory_info().rss
            pre_footprint = 0
            if os.name != "nt":
                pre_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )

            exec_time_start = time.perf_counter()
            function_outputs = self.function(*passed_args, **passed_kwargs)
            exec_time_end = time.perf_counter()
            exec_time = exec_time_end - exec_time_start
            manager.current_stage = None

            post_mem_usage = psutil.Process().memory_info().rss
            post_footprint = 0
            if os.name != "nt":
                post_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )

            # check if caching is about to happen
            caching_necessary = False
            if type(self.outputs) is list:
                for artifact in self.outputs:
                    if artifact.cacher is not None:
                        caching_necessary = True
            else:
                if self.outputs.cacher is not None:
                    caching_necessary = True
            if caching_necessary:
                manager.logger.info("Execution completed, caching outputs...")
            else:
                manager.logger.info("Execution completed")

            post_cache_time_start = time.perf_counter()

            # TODO: special handling for overwrite for cacher?
            # (e.g. run clear first?)
            if type(self.outputs) is list:
                if len(self.outputs) < 1:
                    returns = None
                else:
                    for index, art in enumerate(self.outputs):
                        art.computed = True
                        art.obj = function_outputs[index]
                        manager.record_artifact(art)
                        if art.cacher is not None:
                            art.cacher.save(art.obj)
                    returns = self.outputs
            else:
                art: "cf.artifact.Artifact" = self.outputs
                art.computed = True
                art.obj = function_outputs
                manager.record_artifact(art)
                if art.cacher is not None:
                    art.cacher.save(art.obj)
                returns = art

            # save any reportables if necessary
            if len(self.reportables_list) > 0:
                manager.logger.info("Caching reportables...")
                self._reportables_ready = True  # because we've already run compute
                reportables_artifact = self.reportables
                reportables_artifact.computed = True
                manager.record_artifact(reportables_artifact)
                reportables_artifact.cacher.save(reportables_artifact.obj)

            if caching_necessary:
                manager.logger.info("Caching completed")
                post_cache_time_end = time.perf_counter()
                cache_time = post_cache_time_end - post_cache_time_start
                manager.logger.info(
                    "Timing - execution: %s  caching: %s"
                    % (
                        cf.utils.human_readable_time(exec_time),
                        cf.utils.human_readable_time(cache_time),
                    )
                )
            else:
                manager.logger.info(
                    "Timing - execution: %s" % (cf.utils.human_readable_time(exec_time))
                )

            manager.record_stage_completion(self)
            manager.logger.info(
                f"##### Completed stage {self.contextualized_name} #####"
            )

            if implicit_run:
                self.context._end_implicit_run()

            self.computed = True
            return returns
        except Exception as e:
            e.add_note(f"Was trying to run stage {self.contextualized_name}")
            raise

    def __repr__(self):
        kws = [f"{key}={value!r}" for key, value in self.__dict__.items()]
        return "{}({})".format(type(self).__name__, ", ".join(kws))


def stage(
    *outputs: list["cf.artifact.Artifact"],
    hashing_functions: dict[str, callable] = None,
    pass_self: bool = False,
):
    outputs = list(outputs)  # technically python makes the * a tuple

    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            # return Stage(function, args, kwargs, outputs, hashing_functions, pass_self)
            stage_obj = Stage(
                function, list(args), kwargs, outputs, hashing_functions, pass_self
            )
            return stage_obj

        return wrapper

    return decorator


def run_as_stage(output_names: str | list[str], *inputs):
    outputs = []
    if isinstance(output_names, str):
        outputs.append(cf.artifact.Artifact(output_names))
    else:
        for name in output_names:
            outputs.append(cf.artifact.Artifact(name))

    function = inputs[-1]
    stage_obj = Stage(function, list(inputs[:-1]), {}, [*outputs])
    return stage_obj.outputs


# def single_output(function):
#     """Mini compute step wrapping a single non-cached output. Meant to make it easier to define one-line operations"""
#     @wraps(function)
#     def wrapper(*args, **kwargs):
#         outputs = [cf.artifact.Artifact()]
#         stage_obj = Stage(
#             function, list(args), kwargs, outputs, hashing_functions, pass_self
#         )
