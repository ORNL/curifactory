import copy
import dataclasses
import html
import inspect
import json
from contextlib import chdir
from dataclasses import dataclass, field, make_dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from graphviz import ExecutableNotFound

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
    # outputs: "cf.artifact.ArtifactList" = field(
    #     default_factory=lambda: cf.artifact.ArtifactList("outputs", []),
    #     init=False,
    #     repr=False,
    # )
    outputs: "cf.artifact.ArtifactList" = field(
        default=None,
        init=False,
        repr=False,
    )

    # source: str = None

    def __post_init__(self):

        self._stages = []

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
        # self.map()

        # FILLED BY MANAGER ON RUN:
        self.db_id: UUID = None
        self.start_timestamp = None
        self.end_timestamp = None
        self.reference: str = None
        self.run_number: int = None
        self.commit: str = None
        self.dirty_workdir: bool = False
        self.git_diff: str = None
        self.pip_env: str = None
        self.conda_env: str = None
        self.host_env: dict = None

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
                # print(f"Copying {name}...")
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
        # TODO: may need to base this on _all_ artifacts, not just outputs
        all_artifacts = []
        for stage in self.stages:
            if isinstance(stage.outputs, cf.artifact.Artifact):
                all_artifacts.append(stage.outputs)
            else:
                all_artifacts.extend(stage.outputs)
        # if self.outputs not in all_artifacts:
        #     all_artifacts.append(self.outputs)
        # return cf.artifact.ArtifactFilter(self.outputs.artifact_list())

        # recurse through each one of those sub artifacts
        building_list = []
        for artifact in all_artifacts:
            building_list = artifact.artifact_list(building_list)

        return cf.artifact.ArtifactFilter(building_list)

    @property
    def stages(self):
        return self._stages

    @property
    def leaf_stages(self):
        leaves = []
        for stage1 in self.stages:
            found = False
            for stage2 in self.stages:
                if stage1 == stage2:
                    continue
                if stage1 in stage2.dependencies:
                    found = True
                    break
                for artifact in stage2.artifacts:
                    if stage1 == artifact.compute:
                        found = True
                        break
            if not found:
                leaves.append(stage1)
        return leaves

    @property
    def parameters(self) -> dict[str, Any]:
        params = {}
        for parameter in dataclasses.fields(self):
            if parameter.name not in ["name", "outputs"]:
                params[parameter.name] = getattr(self, parameter.name)
        return params

    @property
    def reportables(self):
        reportables_list = []

        for stage in self.stages:
            if len(stage.reportables.obj) > 0:
                reportables_list.extend(stage.reportables.obj)

        # reportables_list = []
        # handled_stages = []
        # for artifact in self.artifacts:
        #     if artifact.compute is None:
        #         continue
        #     if (
        #         artifact.compute not in handled_stages
        #         and len(artifact.compute.reportables.obj) > 0
        #     ):
        #         reportables_list.extend(artifact.compute.reportables.obj)
        #         handled_stages.append(artifact.compute)
        #
        #     # TODO: test this
        #     # check for any stage dependencies of this artifact's stage
        #     stage_dependencies = [*artifact.compute.dependencies]
        #     # we do this while loop in case there are dependencies of
        #     # dependencies etc.
        #     while len(stage_dependencies) > 0:
        #         dependency = stage_dependencies[0]
        #         if (
        #             dependency not in handled_stages
        #             and len(dependency.reportables.obj) > 0
        #         ):
        #             reportables_list.extend(dependency.reportables.obj)
        #             handled_stages.append(dependency)
        #         stage_dependencies.extend(dependency.dependencies)
        #         stage_dependencies.remove(dependency)

        # STRT: need to also check any stages that don't have artifact outputs
        # (from stage dependencies)

        return reportables_list

    def report(self, template="default_report.html", save: bool = False) -> str:
        manager = cf.get_manager()
        manager.logger.info("Generating pipeline report")
        # TODO: prob have a property for this or something in mnaager rather
        # than asking it to load _here_
        if manager.jinja_environment is None:
            manager.load_jinja_env()

        try:
            map = self.visualize().pipe(format="svg", encoding="utf-8")
        except ExecutableNotFound:
            manager.logger.warning(
                "Graphviz executable not found, pipeline maps may not render"
            )
            map = "<p style='color: red' class='error graphviz'>No graphviz exeuctable found, cannot render map.</p>"

        # render any reportables that need to be rendered
        report_path = Path(manager.reports_path) / self.reference
        report_path.mkdir()

        for reportable in self.reportables:
            # TODO: this def won't work because absolute vs relative, going ot
            # have to os chdir and make a directory per report
            with chdir(str(report_path)):
                reportable.path = "."
                reportable.render()

        template = manager.jinja_environment.get_template(template)
        output = template.render(
            reportables=self.reportables,
            pipeline_name=self.name,
            reference_name=self.reference,
            map=map,
            parameters=html.escape(json.dumps(self.parameters, indent=2, default=str)),
            pipeline_metadata={
                "Database ID": self.db_id,
                "Run number": self.run_number,
                "Start": self.start_timestamp,
                "End": self.end_timestamp,
                "Git commit": self.commit,
            },
            is_dirty=self.dirty_workdir,
            host_env=self.host_env,
            conda_env=self.conda_env,
            pip_env=self.pip_env,
        )

        if save:
            with open(
                str(
                    Path(manager.reports_path)
                    / self.reference
                    / f"{self.reference}.html"
                ),
                "w",
            ) as outfile:
                outfile.write(output)
            cf.reporting.generate_index(save=True)

        return output

    def define(self) -> list["cf.artifact.Artifact"]:
        pass

    # TODO: require new name to be passed?
    def modify(self, **modifications):
        return dataclasses.replace(self, **modifications)

    def map(self):
        """Assumes define() has already run."""
        # TODO: should go based on all artifacts, not just outputs? (probably
        # also needs the leaves first though)
        return self.outputs.map()

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

    # def visualize(self, dot=None, **kwargs):
    #     return self.outputs.visualize(dot, leave_out_context=self.name, **kwargs)

    def visualize(self, dot=None, **kwargs):
        for artifact in self.artifacts:
            # print(artifact, self.outputs)
            # if artifact != self.outputs:
            dot = artifact.visualize(dot, leave_out_context=self.name, **kwargs)
        # return self.outputs.visualize(dot, leave_out_context=self.name, **kwargs)
        for stage in self.stages:
            dot = stage.visualize(dot, leave_out_context=self.name, **kwargs)
        return dot

    def log_verification_checks(self):
        all_good = True
        for entry, verified in self.pre_consolidation_checks.items():
            if not verified:
                all_good = False
        cf.get_manager().logger.info(
            f"Pre-consolidation checks: {'good' if all_good else 'bad'}"
        )
        if not all_good:
            cf.get_manager().logger.warning(
                f"Pre-consolidation checks failed:\n {self.pre_consolidation_checks}"
            )

        all_good = True
        for entry, verified in self.post_consolidation_checks.items():
            if not verified:
                all_good = False
        cf.get_manager().logger.info(
            f"Post-consolidation checks: {'good' if all_good else 'bad'}"
        )
        if not all_good:
            cf.get_manager().logger.warning(
                f"Post-consolidation checks failed:\n {self.post_consolidation_checks}"
            )

    def run(self):
        manager = cf.get_manager()
        manager.current_pipeline_run = self
        manager.current_pipeline_run_target = self.outputs
        # manager.current_pipeline_run_target = None

        self.log_verification_checks()

        # check for overwrites
        overwrites_found = False
        for artifact in self.artifacts:
            if artifact.overwrite:
                overwrites_found = True
                break

        targets = self.leaf_stages
        # TODO: this is probably where we should check for targets reportables
        # too?

        output_artifacts = []
        for target in targets:
            output_artifacts.extend(target.get_output_list())

        need_to_run = False
        for artifact in output_artifacts:
            if (
                artifact.cacher is None
                or not artifact.cacher.check(silent=True)
                or overwrites_found
            ):
                need_to_run = True
                break

        if not need_to_run and len(output_artifacts) > 0:
            # TODO: output_artifacts length check is because if you only ahve
            # one leaf stage that's non-output, we can't load stuff
            # properly...see NOTE: above about targets reportables
            # TODO: this is overly simplistic as multiple leaves could have come
            # from multiple runs
            manager.currently_recording = False
            manager.logger.info("Pipeline outputs already found, re-loading...")

            # find the previous run reference
            metadata = output_artifacts[0].cacher.load_metadata()
            results = manager.search_for_artifact_generating_run(
                metadata["artifact_id"]
            )
            manager.logger.info(f"Collecting outputs from {results['reference']}")
            self.reference = results["reference"]
            self.db_id = results["id"]
            self.run_number = results["run_number"]
            self.start_timestamp = results["start_time"]
            self.end_timestamp = results["end_time"]
            self.commit = results["commit"]
            self.dirty_workdir = results["dirty"]
            self.git_diff = results["git_diff"]
            self.pip_env = results["pip_env"]
            self.conda_env = results["conda_env"]
            self.host_env = results["host_env"]

            for artifact in output_artifacts:
                artifact.get()
            # TODO: also run any non-output stages??
            return self.outputs

        # if (
        #     self.outputs.cacher is not None
        #     and self.outputs.cacher.check(silent=True)
        #     and not overwrites_found
        # ):
        #     manager.currently_recording = False
        #     manager.logger.info("Pipeline outputs already found, re-loading...")
        #
        #     # find the previous run reference
        #     metadata = self.outputs.cacher.load_metadata()
        #     results = manager.search_for_artifact_generating_run(
        #         metadata["artifact_id"]
        #     )
        #     manager.logger.info(f"Collecting outputs from {results['reference']}")
        #     self.reference = results["reference"]
        #     self.db_id = results["id"]
        #     self.run_number = results["run_number"]
        #     self.start_timestamp = results["start_time"]
        #     self.end_timestamp = results["end_time"]
        #
        #     # returns = self.outputs.get()
        #     self.outputs.get()
        #     return self.outputs
        #     # return self.outputs

        manager.currently_recording = True

        manager.logger.info(f"Running pipeline {self.name}")
        manager.record_pipeline_run(self)
        manager.init_file_logging(self.reference)

        # TODO: would need to start file logging here

        # returns = self.outputs.get()
        # if isinstance(self.outputs, list):
        #     returns = []
        #     for art in self.outputs:
        #         # TODO: obviously will need to change once artifact has get()
        #         returns.append(art.compute())
        # else:
        #     returns = self.outputs.compute()

        # self.outputs.get()
        leaves_accounted_for = []
        for artifact in output_artifacts:
            artifact.get()
            if artifact.compute not in leaves_accounted_for:
                leaves_accounted_for.append(artifact.compute)

        for target in targets:
            if target not in leaves_accounted_for:
                target()

        manager.current_pipeline_run = None
        if not manager.error_state:
            manager.record_pipeline_run_completion(self)
        manager.stop_file_logging()

        self.report(save=True)

        # return returns
        return self.outputs

    def compute_hash(self):
        hash_str, hash_debug = self.outputs.compute_hash()
        return hash_str, hash_debug

    def consolidate_shared_artifacts(self):
        """Checks if any involved artifacts are in any way shared/can be explicitly pointed to, one from the other."""
        # TODO: if any artifact contexts are different here, warn?
        replaced = []
        # TODO: not sure if this is the correct place to do this, but ensure
        # that every artifact has a hash_str
        for artifact1 in self.artifacts:
            for artifact2 in self.artifacts:
                if artifact1 == artifact2:  # or artifact2 in replaced:
                    continue
                if artifact1.check_shared_artifact(artifact2):
                    # artifact2.previous_context_names.append(artifact2.
                    # artifact1.previous_context_names.append(artifact2.context.name)
                    for context_name in artifact2.previous_context_names + [
                        artifact2.context.name
                    ]:
                        if (
                            context_name not in artifact1.previous_context_names
                            and context_name != artifact1.context.name
                        ):
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

    @staticmethod
    def load_from_refname(refname: str):
        with cf.get_manager().db_connection() as db:
            pipeline_row = (
                db.sql(f"select * from cf_run where reference = '{refname}'")
                .df()
                .iloc[0]
            )
            target_artifact_row = (
                db.sql(
                    f"select * from cf_artifact where id = '{pipeline_row.target_id}'"
                )
                .df()
                .iloc[0]
            )
        # pipeline = Pipeline(pipeline_row.name)
        pipeline = Pipeline(pipeline_row.reference)
        pipeline.db_id = pipeline_row.id
        pipeline.start_timestamp = pipeline_row.start_time
        pipeline.end_timestamp = pipeline_row.end_time
        pipeline.reference = pipeline_row.reference
        pipeline.run_number = pipeline_row.run_number
        pipeline.commit = pipeline_row.commit
        pipeline.dirty_workdir = pipeline_row.dirty
        pipeline.git_diff = pipeline_row.git_diff
        pipeline.pip_env = pipeline_row.pip_env
        pipeline.conda_env = pipeline_row.conda_env
        pipeline.host_env = pipeline_row.host_env

        cf.get_manager()._pipeline_defining_stack.append(pipeline)
        target_artifact = cf.artifact.Artifact.load_From_uuid(target_artifact_row.id)
        outputs = target_artifact
        cf.get_manager()._pipeline_defining_stack.pop()
        if not isinstance(target_artifact, cf.artifact.ArtifactList):
            pipeline_outputs = cf.artifact.ArtifactList("outputs")

            if type(outputs) is tuple:
                for output in outputs:
                    if isinstance(output, dict):
                        for key, value in output.items():
                            setattr(pipeline, key, value)
                    else:
                        pipeline_outputs.append(output)
            else:
                pipeline_outputs.append(outputs)

            # flatten if single object
            if len(pipeline_outputs) == 1:
                pipeline_outputs = pipeline_outputs[0]
        pipeline.outputs = pipeline_outputs

        return pipeline

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


def pipeline(function):  # noqa: C901
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

        if outputs is None:
            return None

        # TODO: use an artifactfilter instead?
        # pipeline_outputs = cf.artifact.ArtifactList("outputs")
        # pipeline_outputs = cf.artifact.ArtifactFilter(filter_string=f"{self.name}.outputs") # ???

        outputs_list = []

        if type(outputs) is tuple:
            # print("IT's A TUPLE")
            for output in outputs:
                # print(output)
                # if isinstance(output, dict):
                #     for key, value in output.items():
                #         # TODO: eventually add this functionality back in as a
                #         # parameter of the pipeline decorator
                #         setattr(self, key, value)
                if isinstance(output, list):
                    # print("it's a LIST")
                    for sub_output in output:
                        # pipeline_outputs.append(sub_output)
                        outputs_list.append(sub_output)
                elif isinstance(output, cf.artifact.ArtifactList):
                    # print("ITS AN ALIST")
                    for sub_output in output:
                        # pipeline_outputs.append(sub_output)
                        outputs_list.append(sub_output)
                else:
                    outputs_list.append(output)
                    # pipeline_outputs.append(output)
                    # pipeline_outputs.artifacts.append(output)
                    # pipeline_outputs[output.name] = output
        else:
            outputs_list.append(outputs)
            # pipeline_outputs.append(outputs)
            # pipeline_outputs.artifacts.append(outputs)
            # pipeline_outputs[outputs.name] = outputs

        # flatten if single object
        if len(outputs_list) == 1:
            return outputs_list[0]
        else:
            pipeline_outputs = cf.artifact.ArtifactList(
                "outputs", artifacts=outputs_list
            )
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
        def __init__(
            self,
            pipeline_type_name,
            pipeline_field_tuples,
            original_function,
            pipe_dataclass,
        ):
            self.type_name = pipeline_type_name
            # TODO: is type_name necessary? Just change to name
            self.field_tuples = pipeline_field_tuples
            self.original_function = original_function
            self.__doc__ = original_function.__doc__
            self.pipe_dataclass = pipe_dataclass
            cf.get_manager().pipelines[
                self.pipe_dataclass.__name__
            ] = self.pipe_dataclass
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
                            call_parts.append(
                                f"{parameter[0]}: {parameter[1].__name__}"
                            )
                    elif len(parameter) == 3:
                        default_value = parameter[2].default_factory()
                        if isinstance(default_value, str):
                            default_value = f'"{default_value}"'
                        if parameter[1] is Any:
                            call_parts.append(f"{parameter[0]}={default_value}")
                        else:
                            call_parts.append(
                                f"{parameter[0]}: {parameter[1].__name__} = {default_value}"
                            )
                else:
                    call_parts.append(parameter)
            return f"Pipeline {self.type_name}({', '.join(call_parts)})"

    return PipelineFactoryWrapper(
        function.__name__, field_tuples, function, pipeline_dataclass
    )


@dataclass
class PipelineFromRef(Pipeline):
    def __post_init__(self):

        with cf.get_manager().db_connection() as db:
            pipeline_row = (
                db.sql(f"select * from cf_run where reference = '{self.name}'")
                .df()
                .iloc[0]
            )
            self.target_artifact_row = None
            if not pd.isna(pipeline_row.target_id):
                self.target_artifact_row = (
                    db.sql(
                        f"select * from cf_artifact where id = '{pipeline_row.target_id}'"
                    )
                    .df()
                    .iloc[0]
                )
            self.artifact_rows = db.sql(
                f"select * from cf_artifact where run_id = '{pipeline_row.id}'"
            ).df()

        super().__post_init__()

        self.db_id = pipeline_row.id
        self.start_timestamp = pipeline_row.start_time
        self.end_timestamp = pipeline_row.end_time
        self.reference = pipeline_row.reference
        self.run_number = pipeline_row.run_number
        self.name = pipeline_row.pipeline_name
        # TODO: should also grab pipeline_class?
        self.commit = pipeline_row.commit
        self.dirty_workdir = pipeline_row.dirty
        self.git_diff = pipeline_row.git_diff
        self.pip_env = pipeline_row.pip_env
        self.conda_env = pipeline_row.conda_env
        self.host_env = pipeline_row.host_env

    def define(self):

        # make these here and pass into load_from_uuid so we can share them
        # across loading all artifacts/stages and not need to rely on the
        # consolidation step to fix duplicates
        building_stages = {}
        building_artifacts = {}

        artifact_list = []
        for index, artifact_row in self.artifact_rows.iterrows():
            artifact = cf.artifact.Artifact.load_from_uuid(
                artifact_row.id, building_stages, building_artifacts
            )
            artifact_list.append(artifact)

        # get the outputs if relevant?
        # outputs = None
        # print("Checking for outputs")
        # for artifact in artifact_list:
        #     print(artifact)
        #     if artifact.name == "outputs" and artifact.compute in self.leaf_stages:
        #         outputs = artifact
        #         break
        #
        # return outputs

        if self.target_artifact_row is not None:
            target_artifact = cf.artifact.Artifact.load_from_uuid(
                self.target_artifact_row.id, building_stages, building_artifacts
            )
            outputs = target_artifact

            pipeline_outputs = cf.artifact.ArtifactList("outputs")

            if type(outputs) is tuple:
                for output in outputs:
                    if isinstance(output, dict):
                        for key, value in output.items():
                            setattr(pipeline, key, value)
                    # elif isinstance(output, cf.artifact.ArtifactList):
                    #     for sub_output in output:
                    #         pipeline_outputs.append(sub_output)
                    else:
                        pipeline_outputs.append(output)
            else:
                pipeline_outputs.append(outputs)

            # flatten if single object
            if len(pipeline_outputs) == 1:
                pipeline_outputs = pipeline_outputs[0]
            return pipeline_outputs
        return None
