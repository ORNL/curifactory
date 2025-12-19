import copy
import dataclasses
import inspect
from dataclasses import dataclass, field, make_dataclass
from typing import Any
from uuid import UUID

import curifactory.experimental as cf


@dataclass
class Pipeline:
    name: str
    # artifacts: "artifact.ArtifactManager" = field(default_factory=lambda: artifact.ArtifactManager(), init=False, repr=False)
    # artifacts: "artifact.ArtifactFilter" = field(default_factory=lambda: artifact.ArtifactFilter(), init=False, repr=False)

    # NOTE: keep in mind context/context_mine are always changing based on
    # whatever called it last, this needs to be recomputed whenever needed?
    # TODO: (6/20/24) I think context and and context_name can be removed,
    # context is determined through frame inspection in the artifacts themselves
    # and I think that makes a lot more sense?
    # context: "Experiment" = field(default=None, init=False, repr=False)
    # context_name: str = field(default=None, init=False, repr=False)

    # TODO: maybe outputs should be redefined to output since that can mean both
    # plural and singular (we auto-flatten in the @experiment dec)
    outputs: "cf.artifact.ArtifactList" = field(
        default_factory=lambda: cf.artifact.ArtifactList("outputs", []),
        init=False,
        repr=False,
    )

    # source: str = None

    def __post_init__(self):

        cf.get_manager()._pipeline_defining_stack.append(self)
        self.ensure_context_copies()
        definition_outputs = self.define()
        cf.get_manager()._pipeline_defining_stack.pop()

        # TODO: I don't actually think outputs needs to be an artifact list
        # TODO TODO we need to determine if there's more than one output, in
        # which case yes make it an ArtifactList, but self.output should always
        # be an artifact?
        # if not isinstance(definition_outputs, artifact.ArtifactList) and :
        #     definition_outputs = artifact.ArtifactList("outputs", definition_outputs)
        self.outputs = definition_outputs
        self.map()

        # FILLED BY MANAGER ON RUN:
        self.db_id: UUID = None
        self.start_timestamp = None
        self.end_timestamp = None
        self.reference: str = None
        self.run_number: int = None

        # cf.get_manager().parameterized_pipelines[self.__class__].append(self)

        self.pre_consolidation_checks = self.verify()
        self.consolidate_shared_artifacts()
        self.post_consolidation_checks = self.verify()

    def verify(self):
        checks = {}
        for artifact in self.artifacts:
            checks[f"{artifact.contextualized_name}_{id(artifact)}"] = artifact.verify()
        return checks

    def ensure_context_copies(self):
        """An experiment definition, when taking other pipelines or artifacts as parameters,
        shouldn't mutate or alter where those pipelines/artifacts come from - so anything passed
        in gets automatically copied instead."""

        for name, value in self.parameters.items():
            if isinstance(value, (Pipeline, cf.artifact.Artifact)):
                setattr(self, name, value.copy())
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, (Pipeline, cf.artifact.Artifact)):
                        value[index] = item.copy()
            elif isinstance(value, dict):
                for key, value_j in value.items():
                    if isinstance(value_j, (Pipeline, cf.artifact.Artifact)):
                        value[key] = value_j.copy()

    @property
    def artifacts(self):
        return cf.artifact.ArtifactFilter(self.outputs.artifact_list())

    @property
    def parameters(self) -> dict[str, Any]:
        params = {}
        for parameter in dataclasses.fields(self):
            if parameter.name not in ["name", "outputs"]:
                params[parameter.name] = getattr(self, parameter.name)
        return params

    def define(self) -> list["cf.artifact.Artifact"]:
        pass

    # TODO: require new name to be passed?
    def modify(self, **modifications):
        return dataclasses.replace(self, **modifications)

    def map(self):
        """Assumes define() has already run."""
        return

        # TODO: do any necessary collapsing of sufficiently equivalent artifacts

        for art in self.outputs:
            # if there are any artifacts not from this artifact manager, make a
            # copy that is
            # if art.context is not None and != self.artifacts
            if art.context != self.artifacts:
                pass

                # TODO: make copy (recursive)

        # for art in self.outputs:
        #     self.artifacts.artifacts[art.name] = art
        #
        #     for arg in art.compute.

        # TODO TODO TODO this is where we add to the local artifact manager
        # outputs = self.outputs
        # outputs.context = self
        # outputs.context_name = "outputs"
        # artifact.Artifacts.artifacts[outputs.filter_name()] = outputs
        # for art in self.outputs:
        #     # TODO: unclear if the context/context_name is the right approach
        #     art.context = self
        #     art.context_name = name

    def _implicit_run(self):
        """If an artifact from this pipeline is manually retrieved and a compute
        step is required, start an implicit run with that artifact as the target."""
        manager = cf.get_manager()
        manager.currently_recording = True
        manager.logger.info(f"Running partial pipeline {self.name}")
        manager.record_pipeline_run(self)
        manager.current_pipeline_run = self

    def _end_implicit_run(self):
        manager = cf.get_manager()
        manager.current_pipeline_run = None
        manager.record_pipeline_run_completion(self)

    def visualize(self, dot=None, **kwargs):
        return self.outputs.visualize(dot, leave_out_context=self.name, **kwargs)

    def log_verification_checks(self):
        all_good = True
        for entry, verified in self.pre_consolidation_checks.items():
            if not verified:
                all_good = False
        cf.get_manager().logger.info(f"Pre-consolidation checks: {'good' if all_good else 'bad'}")
        if not all_good:
            cf.get_manager().logger.warn(f"Pre-consolidation checks failed:\n {self.pre_consolidation_checks}")

        all_good = True
        for entry, verified in self.post_consolidation_checks.items():
            if not verified:
                all_good = False
        cf.get_manager().logger.info(f"Post-consolidation checks: {'good' if all_good else 'bad'}")
        if not all_good:
            cf.get_manager().logger.warn(f"Post-consolidation checks failed:\n {self.post_consolidation_checks}")

    def run(self):
        manager = cf.get_manager()
        manager.current_pipeline_run = self
        manager.current_pipeline_run_target = self.outputs

        self.log_verification_checks()

        if self.outputs.cacher is not None and self.outputs.cacher.check(silent=True):
            manager.currently_recording = False
            manager.logger.info("Pipeline outputs already found, re-loading...")

            # find the previous run reference
            metadata = self.outputs.cacher.load_metadata()
            results = manager.search_for_artifact_generating_run(metadata["artifact_id"])
            manager.logger.info(f"Collecting outputs from {results["reference"]}")

            returns = self.outputs.get()
            return self.outputs

        manager.currently_recording = True

        manager.logger.info(f"Running pipeline {self.name}")
        manager.record_pipeline_run(self)

        returns = self.outputs.get()
        # if isinstance(self.outputs, list):
        #     returns = []
        #     for art in self.outputs:
        #         # TODO: obviously will need to change once artifact has get()
        #         returns.append(art.compute())
        # else:
        #     returns = self.outputs.compute()

        manager.current_pipeline_run = None
        manager.record_pipeline_run_completion(self)
        # return returns
        return self.outputs

    def compute_hash(self):
        hash_str, hash_debug = self.outputs.compute_hash()
        return hash_str, hash_debug

    def consolidate_shared_artifacts(self):
        """Checks if any involved artifacts are in any way shared/can be explicitly pointed to, one from the other."""
        # TODO: if any artifact contexts are different here, warn?
        replaced = []
        for artifact1 in self.artifacts:
            for artifact2 in self.artifacts:
                if artifact1 == artifact2:  # or artifact2 in replaced:
                    continue
                if artifact1.check_shared_artifact(artifact2):
                    # artifact2.previous_context_names.append(artifact2.
                    #artifact1.previous_context_names.append(artifact2.context.name)
                    for context_name in artifact2.previous_context_names + [artifact2.context.name]:
                        if context_name not in artifact1.previous_context_names and context_name != artifact1.context.name:
                            artifact1.previous_context_names.append(context_name)
                    artifact2.replace(artifact1)
                    # shared = artifact1.copy()
                    # # artifact2.replace(artifact1.copy())
                    # artifact1.replace(shared)
                    # artifact2.replace(shared)
                    # replaced.append(artifact1)
                    replaced.append(artifact2)

    def _inner_copy(
        self,
        building_stages: dict["cf.stage.Stage", "cf.stage.Stage"] = None,
        building_artifacts: dict["cf.artifact.Artifact", "cf.artifact.Artifact"] = None,
    ):
        new_pipeline = self.modify()
        # if building_stages is None:
        #     building_stages = {}
        # if building_artifacts is None:
        #     building_artifacts = {}
        #
        # new_pipeline.outputs = new_pipeline.outputs.copy()
        return new_pipeline

    def copy(self):
        return self._inner_copy(None, None)

    # TODO: (3/17/2024) override setattr and essentially make the fields frozen
    # - if you try to modify an pipeline parameter, that won't necessarily
    # auto apply to the stages it's used in because we have no direct way of
    # knowing which stages it was used in.

    # def __setattr__(self, name: str, value):
    #     # TODO: this has a lot of potential flaws,
    #     # 1. I don't think we actually need a filter_name here, we should (in
    #     # theory?) be able to get the full attribute access list maybe? I guess
    #     # we can't get _this_ pipeline's parents, so I suppose this works as
    #     # long as we understand that context should really only be used for this
    #     # exact thing, it's not a stable concept? (alternatively, it can be made
    #     # more concrete during an actual pipeline run())
    #     # 2. This won't handle lists of artifacts I don't think?
    #     # IDEA: this should probably be handled by a map() call instead that
    #     # searches for any sub objects of type Artifact/pipeline
    #     if isinstance(value, artifact.Artifact):
    #         print(f"Setting context name of {value.name} to {name}")
    #         value.context = self
    #         value.context_name = name
    #         artifact.Artifacts.artifacts[value.filter_name()] = value
    #     if isinstance(value, pipeline) and name != "context":
    #         print(f"Setting context name of {value.name} to {name}")
    #         value.context = self
    #         value.context_name = name
    #         # oooh I don't like this, better way?
    #         for item in dir(value):
    #             value_attr = getattr(value, item)
    #             if isinstance(value_attr, artifact.Artifact):
    #                 print(f"Setting sub-pipeline context name for {item}")
    #                 artifact.Artifacts.artifacts[value_attr.filter_name()] = value_attr
    #
    #     super().__setattr__(name, value)
    #
    # def filter_name(self) -> str:
    #     if self.context is not None:
    #         this_name = self.name if self.context_name is None else self.context_name
    #         return f"{self.context.filter_name()}.{this_name}"
    #     return self.name


def pipeline(function):
    # make the fields based on the function signature
    field_tuples = []
    parameters = inspect.signature(function).parameters
    for key in parameters.keys():
        annotation = parameters[key].annotation
        default = parameters[key].default
        if annotation == inspect._empty and default == inspect._empty:
            # a plain parameter `my_function(some_param)`
            field_tuples.append(key)
        elif annotation == inspect._empty:
            # a parameter with a default but no type
            # `my_function(some_param='yeah')`
            copied_default = copy.deepcopy(default)
            field_tuples.append(
                (
                    key,
                    Any,
                    field(
                        default_factory=lambda new_val=copied_default: new_val,
                        init=True,
                        repr=True,
                    ),
                )
            )
        elif default == inspect._empty:
            # a parameter with a type but no default
            # `my_function(some_param: int)`
            field_tuples.append((key, annotation))
        else:
            # a parameter with type and default
            # `my_function(some_param: int=5)`
            copied_default = copy.deepcopy(default)
            field_tuples.append(
                (
                    key,
                    annotation,
                    field(
                        default_factory=lambda new_val=copied_default: new_val,
                        init=True,
                        repr=True,
                    ),
                )
            )

    def define(self):
        # populate the actual function params call with the self.param versions
        kwargs = {
            param_name: getattr(self, param_name)
            for param_name in list(parameters.keys())
        }

        # call the function that this pipeline is wrapping (defines the
        # artifacts flow)
        outputs = function(**kwargs)

        # TODO: use an artifactfilter instead?
        pipeline_outputs = cf.artifact.ArtifactList("outputs")
        # pipeline_outputs = cf.artifact.ArtifactFilter(filter_string=f"{self.name}.outputs") # ???
        if type(outputs) is tuple:
            for output in outputs:
                if isinstance(output, dict):
                    for key, value in output.items():
                        setattr(self, key, value)
                else:
                    pipeline_outputs.append(output)
                    # pipeline_outputs.artifacts.append(output)
                    # pipeline_outputs[output.name] = output
        else:
            pipeline_outputs.append(outputs)
            # pipeline_outputs.artifacts.append(outputs)
            # pipeline_outputs[outputs.name] = outputs

        # flatten if single object
        if len(pipeline_outputs) == 1:
            pipeline_outputs = pipeline_outputs[0]
        return pipeline_outputs

    pipeline_dataclass = make_dataclass(
        function.__name__,
        field_tuples,
        bases=(Pipeline,),
        namespace={"define": define, "function": function},
    )

    # def wrapper(*args, **kwargs):
    #     return pipeline_dataclass(*args, **kwargs)
    #
    # wrapper.parameters = field_tuples
    # wrapper.__repr__ = lambda: f"{function.__name__}({','.join([name + ': ' + str(type_str) for name, type_str in field_tuples])})"
    #
    # return wrapper

    class PipelineFactoryWrapper:
        def __init__(self, pipeline_type_name, pipeline_field_tuples, original_function, pipe_dataclass):
            self.type_name = pipeline_type_name
            # TODO: is type_name necessary? Just change to name
            self.field_tuples = pipeline_field_tuples
            self.original_function = original_function
            self.__doc__ = original_function.__doc__
            self.pipe_dataclass = pipe_dataclass
            cf.get_manager().pipelines[self.pipe_dataclass.__name__] = self.pipe_dataclass
            cf.get_manager().parameterized_pipelines[pipeline_dataclass] = []

        def __call__(self, *args, **kwargs):
            # parameterized_pipeline = pipeline_dataclass(*args, **kwargs)
            parameterized_pipeline = self.pipe_dataclass(*args, **kwargs)
            parameterized_pipeline.__doc__ = self.__doc__
            return parameterized_pipeline

        @property
        def parameters(self) -> dict[str, Any]:
            params = {}
            for parameter in self.field_tuples:
                if isinstance(parameter, tuple):
                    if len(parameter) == 3:
                        params[parameter[0]] = parameter[2].default_factory()
                    else:
                        params[parameter[0]] = None
                else:
                    params[parameter] = None
            return params

        def __repr__(self):
            call_parts = ["name: str"]
            for parameter in self.field_tuples:
                if isinstance(parameter, tuple):
                    if len(parameter) == 2:
                        if parameter[1] is Any:
                            call_parts.append(f"{parameter[0]}")
                        else:
                            call_parts.append(f"{parameter[0]}: {parameter[1].__name__}")
                    elif len(parameter) == 3:
                        default_value = parameter[2].default_factory()
                        if isinstance(default_value, str):
                            default_value = f"\"{default_value}\""
                        if parameter[1] is Any:
                            call_parts.append(f"{parameter[0]}={default_value}")
                        else:
                            call_parts.append(f"{parameter[0]}: {parameter[1].__name__} = {default_value}")
                else:
                    call_parts.append(parameter)
            return f"Pipeline {self.type_name}({', '.join(call_parts)})"

    return PipelineFactoryWrapper(function.__name__, field_tuples, function, pipeline_dataclass)
