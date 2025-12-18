# from simplification.experiment import Experiment
# from simplification.stage import Stage
import copy
import inspect
import logging
from functools import partial
from uuid import UUID

import duckdb
import pandas as pd
from graphviz import Digraph

import curifactory.experimental as cf


def pointer_based_property_getter(self, name):
    if self.pointer is not None:
        return getattr(self.pointer, name)
    return getattr(self, f"_{name}")


def pointer_based_property_setter(self, value, name):
    if self.pointer is not None:
        setattr(self.pointer, name, value)
    else:
        setattr(self, f"_{name}", value)


def pointer_based_property(name):
    return property(
        partial(pointer_based_property_getter, name=name),
        partial(pointer_based_property_setter, name=name),
    )


class ArtifactManager:
    # TODO: possibly needs a name?
    def __init__(self):
        # self.artifacts: dict[str, Artifact | ArtifactManager] = {}
        # pass
        self.artifacts: list[Artifact] = []

    def __getitem__(self, key):
        return self.artifacts[key]

    # def __setitem__(self, key, value):
    #     pass

    def display(self):
        for artifact in self.artifacts:
            print(artifact)


Artifacts = ArtifactManager()  # TODO: set up as part of global config?
# config should be accessible via cf.config? And that gets set from commandline,
# but both library and cli have a default
# TODO: IDEA: IDEA: perhaps a better way of creating the artifacts map is to rely on an
# explicit map() function on experiment that iterates backwards through each
# final artifact's compute chain and adds the appropriate table reference (then
# we don't have to worry about the artifact having filter_name) and we have a
# (possibly) less dodgy settattr on experiment.
# Experiment names could still be implicitly tracked on instantiation, which
# would then potentially allow more direct control over how/what gets mapped.


# TODO: is it possible to add our own type [] thing, so someone could say:
# Artifact[pytorch.Module]
class Artifact:
    internal_id = pointer_based_property("internal_id")
    name = pointer_based_property("name")
    cacher = pointer_based_property("cacher")
    obj = pointer_based_property("obj")
    computed = pointer_based_property("computed")
    compute = pointer_based_property("compute")
    hash_str = pointer_based_property("hash_str")
    hash_debug = pointer_based_property("hash_debug")
    previous_context_names = pointer_based_property("previous_context_names")
    context = pointer_based_property("context")

    db_id = pointer_based_property("db_id")
    generated_time = pointer_based_property("generated_time")
    reportable = pointer_based_property("reportable")

    in_db = pointer_based_property("in_db")
    in_cache = pointer_based_property("in_cache")

    overwrite = pointer_based_property("overwrite")

    def __init__(self, name=None, cacher=None):
        self.pointer = None

        self._internal_id = id(self)

        self._name = name
        self._cacher = cacher
        self._obj = None

        self._computed: bool = False

        # TODO: these should probably be properties that just return the
        # compute stage's hash str
        self._hash_str = None
        self._hash_debug = None

        self._compute: cf.stage.Stage = None

        # previous context names means every time we copy an artifact into a
        # new context, we assign the
        self._previous_context_names: list[str] = []
        self._context: cf.experiment.Experiment = None
        # self.context: ArtifactManager = None
        # self.original_context:
        # self.context_name: str = None

        self.context = self._find_context()
        self._add_to_context()

        self._db_id: UUID = None
        self._generated_time = None
        self._reportable: bool = False

        self._overwrite: bool = False

        # the reason I'm hesitant to explicitly track dependents is that someone
        # could theoretically define a custom experiment dataclass and do weird
        # things like set one of the artifacts as a class variable, which
        # wouldn't be caught? Quite frankly that's such a ridiculous use case
        # though, that I don't think that's realistically going to be an issue.
        # TODO: the better way to do this once artifacts are auto-added to the
        # context's artifactmanager might be to just check args of compute stage
        # of every artifact in the manager
        # self.dependents: list[stage.Stage] = []

    def __eq__(self, o):
        return self.internal_id == o.internal_id

    def _find_context(self) -> "cf.experiment.Experiment":
        # print("Seeking context for artifact ", self.name, cf.get_manager()._experiment_defining_stack)
        if len(cf.get_manager()._experiment_defining_stack) > 0:
            # self.context = cf.get_manager()._experiment_defining_stack[-1]
            return cf.get_manager()._experiment_defining_stack[-1]
            # print("Context: ", self.context.name)
        return None
        # TODO: check if context is none first?
        # for frame in inspect.stack():
        #     if "self" in frame.frame.f_locals.keys() and isinstance(
        #         frame.frame.f_locals["self"], cf.experiment.Experiment
        #     ):
        #         # print("FOUND THE EXPERIMENT")
        #         return frame.frame.f_locals["self"]
        # return None
        #

    # TODO: if experiment.artifacts is just filter of outputs, we may not
    # actually need this at all
    def _add_to_context(self):
        """Add this artifact to the context experiment's artifact manager."""
        # if self.context is None:
        #     Artifacts.artifacts.append(self)
        # else:
        #     self.context.artifacts.artifacts.append(self)
        pass

    def compute_hash(self):
        if self.compute is None:
            return ""
        self.hash_str, self.hash_debug = self.compute.compute_hash()
        return self.hash_str, self.hash_debug

    def check_shared_artifact(self, other_artifact):
        """Two artifacts are considered equivalent (can be shared) if their hash and name is the same"""
        # TODO: is it a problem to use hash_str directly instead of compute_hash?
        if (
            self.name == other_artifact.name
            and self.hash_str == other_artifact.hash_str
        ):
            return True
        return False

    def __setattr__(self, name: str, value):
        # pass a reference for this artifact to the cacher so it can access info
        # like the artifact name etc.
        if name == "cacher" and value is not None:
            # TODO: unclear if this is now broken because of the pointer logic
            value.artifact = self
        super().__setattr__(name, value)

    def __repr__(self):
        # TODO: think through better set of things to show
        string = f"Artifact '{self.name}'"
        if self.obj is not None:
            display_str = ": "

            manager = cf.get_manager()
            display_str += manager.get_artifact_obj_repr(self)
            string += display_str
        return string

    def get_from_db(self):
        pass

    def determine_overwrite(self) -> bool:
        """If any artifacts upstream from this one have overwrite specified,
        this artifact needs to be overwritten as well."""
        for artifact in self.artifact_list():
            if artifact.overwrite:
                return True
        return False

    def get(self):
        try:
            # Note that computed is set by the _stage_
            if self.computed:
                return self.obj
            overwrite = self.determine_overwrite()
            if self.cacher is not None and not overwrite:
                if self.cacher.check():
                    self.obj = self.cacher.load()
                    # TODO: metadata stuff
                    return self.obj

            # if this artifact is requested and no current target, that means
            # this is the target if a new run has to start
            manager = cf.get_manager()
            if manager.current_experiment_run_target is None:
                manager.current_experiment_run_target = self
            # (we handle associating the ID with the experiment run during
            # record_artifact)

            if overwrite:
                manager.logger.info(f"Will overwrite artifact {self.name}")

            self.compute()
            # NOTE: stage handles running cachers
            return self.obj
        except Exception as e:
            e.add_note(f"Was trying to retrieve artifact {self.name}")
            raise

    @property
    def context_name(self):
        current = "None"
        if self.context is not None:
            current = self.context.name
        if len(self.previous_context_names) > 0:
            current += f" ({','.join(self.previous_context_names)})"
        return current

    @property
    def artifacts(self):
        # TODO: not sure which of these is more correct
        # return ArtifactFilter(self.artifact_list())
        return ArtifactFilter([self])

    # def replace(self, artifact):
    #     self.pointer = artifact
    def replace(self, artifact):
        # TODO: check for differing contexts and warn as applicable
        # hmm so this only makes sense if we know what the actual "current"
        # context is, we don't want to replace another context's artifact
        # without warning, but it would be quite fine to replace one of this
        # context's artifact with one from another. I think we can just use
        # _find_context again

        current_context = self._find_context()
        if (
            current_context != self.context
            and current_context is not None
            and self.context is not None
        ):
            logging.warning(
                "Context %s is replacing an artifact (%s) owned by a different context %s. Recommend using a .copy()",
                current_context.name,
                self.name,
                self.context.name,
            )
        # TODO: might be useful to track the frame/line/file that this
        # replacement is called from, could help debugging if spit out in the
        # logs

        if artifact == self:
            self.pointer = None
            logging.warning("Replacing self with self")
            return

        # TODO: replace all attributes of this artifact with the other one
        # (prob also need a variable to directly point to the other one? That
        # way if when compute/get is called on this one we can check if it
        # already was or not and just return that)
        # self.name = artifact.name
        # self.cacher = artifact.cacher
        # self.object = artifact.object
        # self.hash_str = artifact.hash_str
        # self.hash_debug = artifact.hash_debug
        # self.compute = artifact.compute
        self.pointer = artifact
        # for stage in self.dependents:
        #     for i, arg in enumerate(stage.args):
        #         if arg == self:
        #             stage.args[i] = artifact
        #     for key in stage.kwargs:
        #         if stage.kwargs[key] == self:
        #             stage.kwargs[key] = artifact
        # if self in stage.args:
        #     stage.args.rep

        # TODO: remove self from context?

        # when we replace an artifact, we only need to search _forward_ for
        # stage args to replace.

    def _inner_copy(
        self,
        building_stages: dict["cf.stage.Stage", "cf.stage.Stage"] = None,
        building_artifacts: dict["cf.artifact.Artifact", "cf.artifact.Artifact"] = None,
    ):
        if building_stages is None:
            building_stages = {}
        if building_artifacts is None:
            building_artifacts = {}

        if self.internal_id in building_artifacts.keys():
            return building_artifacts[self.internal_id]

        artifact = Artifact(self.name)
        building_artifacts[self.internal_id] = artifact
        artifact.cacher = copy.deepcopy(self.cacher)
        artifact.obj = self.obj
        artifact.hash_str = self.hash_str
        artifact.hash_debug = self.hash_debug
        if self.compute is not None:
            artifact.compute = self.compute._inner_copy(
                building_stages, building_artifacts
            )
            if not isinstance(artifact.compute.outputs, list):
                artifact.compute.outputs = artifact
            else:
                # if it's a list, this artifact was only one of multiple
                # outputs, so search through and replace just the one with the
                # same name
                for index, output in enumerate(artifact.compute.outputs):
                    # print("Changing multioutputs for stage", artifact.compute.name
                    if output.name == self.name:
                        artifact.compute.outputs[index] = artifact
        artifact.previous_context_names = [*self.previous_context_names]

        # print(self.context.name)
        if (
            self.context is not None
            and self.context.name not in artifact.previous_context_names
            and (
                artifact.context is not None
                and artifact.context.name != self.context.name
            )
        ):
            # print("Adding", self.context.name)
            # print(artifact.context_name)
            artifact.previous_context_names.append(self.context.name)
        return artifact

    def copy(self):
        return self._inner_copy(None, None)
        # artifact = Artifact(self.name)
        # artifact.cacher = copy.deepcopy(self.cacher)
        # artifact.obj = self.obj
        # artifact.hash_str = self.hash_str
        # artifact.hash_debug = self.hash_debug
        # if self.compute is not None:
        #     artifact.compute = self.compute.copy()  # TODO: still wrong I think
        #     artifact.compute.outputs = self
        # artifact.previous_context_names = [*self.previous_context_names]
        # # TODO: ... so we need a new compute though, because the output artifact
        # # will now be wrong.
        #
        # # TODO: put current context name into previous contexts, then replace
        # # context?
        # if self.context is not None:
        #     artifact.previous_context_names.append(self.context.name)
        # return artifact

    def artifact_tree(self):
        return self.compute._artifact_tree()

    def dependencies(self) -> list["Artifact"]:
        """Gets any input artifacts from the compute stage."""
        artifact_dependencies = []
        for arg in self.compute._combined_args():
            if isinstance(arg, Artifact):
                artifact_dependencies.append(arg)
        for stage in self.compute.dependencies:
            for arg in stage._combined_args():
                if isinstance(arg, Artifact):
                    artifact_dependencies.append(arg)
        return artifact_dependencies

    def artifact_list(self, building_list: list = None):
        """Recursively builds a list of _all_ artifacts prior to this one."""
        if building_list is None:
            building_list = []
        building_list.append(self)

        # TODO: TODO: TODO: this should be based on .dependencies...right?
        for artifact in self.dependencies():
            if artifact not in building_list:
                building_list = artifact.artifact_list(building_list)
            # if isinstance(arg, Artifact) and arg not in building_list:
        # for arg in self.compute._combined_args():
        #     if isinstance(arg, Artifact) and arg not in building_list:
        #         building_list = arg.artifact_list(building_list)
        # building_list.append(arg)
        # if isinstance(arg, ArtifactList):
        #     for list_artifact in arg.artifacts:
        #         print(list_artifact)
        #         building_list = list_artifact.artifact_list(building_list)

        return building_list

    def artifact_list_debug(self):
        # TODO: outdated, mimic artifact_list above
        artifacts = self.artifact_list()
        for artifact in artifacts:
            artifact.compute_hash()
            print("----")
            print(
                artifact.name,
                "-",
                artifact.compute.function.__name__,
                "-",
                artifact.hash_str,
            )
            print(artifact.hash_debug)

    # def filter(self, artifact_name=None, context_name=None, stage_name=None) -> list["Artifact"]:
    def filter(self, search_str: str) -> "ArtifactFilter":
        results = []
        for artifact in self.dependencies():
            if (
                artifact.name == search_str
                or (
                    artifact.context is not None and artifact.context.name == search_str
                )
                or (
                    artifact.compute is not None and artifact.compute.name == search_str
                )
                or search_str in artifact.previous_context_names
            ):
                if artifact not in results:
                    results.append(artifact)
            sub_results = artifact.filter(search_str).artifacts
            for result in sub_results:
                if result not in results:
                    results.append(result)
        return ArtifactFilter(results, search_str)

    # TODO: make this _ function to indicate shouldn't be called outside of cf
    # code
    # def filter_name(self) -> str:
    #     if self.context is not None:
    #         this_name = self.name if self.context_name is None else self.context_name
    #         return f"{self.context.filter_name()}.{this_name}"
    #     return self.name

    @staticmethod
    def from_metadata(metadata=None, path=None):
        # TODO
        pass

    @staticmethod
    def from_cacher(cacher):
        # TODO: effectively allows specifying a raw file path as an artifact
        # that you want as your initial "input"
        pass

    @staticmethod
    def from_list(name, artifacts):
        # combined = _aggregate_artifact_list(*artifacts)
        # combined.outputs[0].name = name
        # # TODO: getattr(combined, name) will not return correct thing
        # return combined.outputs[0]
        return ArtifactList(name, artifacts)

    def _node(self, dot):
        self.compute_hash()
        if self.name is not None:
            str_name = str(
                self.name
                + "\n"
                + self.hash_str[:6]
                # self.name + "\n" + self.context_name + "\n" + self.hash_str[:6]
            )
        else:
            # str_name = str("NONE\n" + self.context_name + "\n" + self.hash_str[:6])
            str_name = str("NONE\n" + self.hash_str[:6])

        context_names = ",".join(self.previous_context_names)

        dot.node(
            name=str(self.internal_id),
            label=str_name,
            shape="box",
            fontsize="8.0",
            height=".25",
            # xlabel=self.context_name,
            xlabel=context_names,
        )

    def visualize(self, dot=None):
        if dot is None:
            dot = cf.utils.init_graphviz_graph()

        self._inner_visualize(dot)
        return dot

    def _inner_visualize(self, g):
        self._node(g)

        self.compute.visualize(g)
        if (str(id(self.compute)), str(self.internal_id)) not in g._edges:
            g.edge(str(id(self.compute)), str(self.internal_id))
            g._edges.append((str(id(self.compute)), str(self.internal_id)))

        # for dependency in self.dependencies():
        #     # don't add duplicate edges (can happen when visualizing from a
        #     # filter)
        #     if (str(dependency.internal_id), str(self.internal_id)) not in g._edges:
        #         g.edge(str(dependency.internal_id), str(self.internal_id))
        #         g._edges.append((str(dependency.internal_id), str(self.internal_id)))
        #     g = dependency._visualize(g)

        return g


class ArtifactFilter:
    def __init__(self, starting_artifacts=None, filter_string=""):
        if starting_artifacts is None:
            starting_artifacts = []
        self.artifacts = starting_artifacts
        self.filter_string = filter_string

    def __repr__(self):
        # TODO: should probably add something to distinguish this from a true
        # list
        return repr(self.artifacts)

    def replace(self, new_artifact):
        # TODO: more complex logic for if self is list and artifact is list etc
        for artifact in self.artifacts:
            if artifact != new_artifact:
                artifact.replace(new_artifact)

    def _inner_copy():
        pass

    def copy(self):
        # ArtifactFilter()
        copied_artifacts = []
        building_artifacts = {}
        building_stages = {}
        for artifact in self.artifacts:
            copied_artifacts.append(
                artifact._inner_copy(building_stages, building_artifacts)
            )
        return ArtifactFilter(copied_artifacts)

    # TODO: if the starting_artifacts is a single artifact, just call filter on
    def filter(self, search_str: str) -> "ArtifactFilter":
        results = []

        while "." in search_str:
            next_str = search_str.split(".")[0]
            remaining = ".".join(search_str.split(".")[1:])
            next_step = self.filter(next_str).filter(remaining)
            return next_step

        # TODO: check for index?
        # if search_str.prefix

        for artifact in self.artifacts:
            if (
                artifact.name == search_str
                or (
                    artifact.context is not None and artifact.context.name == search_str
                )
                or (
                    artifact.compute is not None and artifact.compute.name == search_str
                )
                or search_str in artifact.previous_context_names
            ):
                if artifact not in results:
                    results.append(artifact)
            sub_results = artifact.filter(search_str).artifacts
            for result in sub_results:
                if result not in results:
                    results.append(result)
        return ArtifactFilter(results, f"{self.filter_string}.{search_str}")

    def _visualize(self):
        dot = None
        for artifact in self.artifacts:
            dot = artifact._visualize(dot)
        return dot

    def resolve(self) -> "Artifact":
        if len(self.artifacts) == 1:
            return self.artifacts[0]
        else:
            return ArtifactList(artifacts=self.artifacts)

    def list(self):
        """TODO: maybe this should return ArtifactList instead?"""
        return self.artifacts

    def __getattr__(self, name):
        return self.filter(name)

    # TODO: setattr that detects if trying to assign to a filter and errors if
    # so (tell to use .replace instead)

    def __getitem__(self, key):
        return self.artifacts[key]

    def __setitem__(self, key, item):
        self.artifacts[key] = item

    def __len__(self):
        return len(self.artifacts)


# TODO: in order to avoid duplicating hashing logic, maybe this will still need
# to use the aggregate_artifact_list stage, but it'll be set up better than the
# from_list method above. And since this is a special type, it'll be easier to
# filter out weird "aggregate_artifact_list" names in list of executed stages.
# (making it almost an implicit stage)
class ArtifactList(Artifact):  # , list):
    def __init__(self, name: str = None, artifacts=None):
        super().__init__(name)
        if artifacts is None:
            artifacts = []
        self.inner_artifact_list = artifacts
        self.compute = cf.stage.Stage(
            function=_aggregate_artifact_list,
            args=self.inner_artifact_list,
            kwargs={},
            outputs=[Artifact(name=self.name)],
        )
        self.compute.outputs = self
        self.cacher = cf.caching.AggregateArtifactCacher()

    def __repr__(self):
        return f"ArtifactList('{self.name}', {repr(self.inner_artifact_list)})"

    def __getitem__(self, key):
        return self.inner_artifact_list[key]

    def __setitem__(self, key, item):
        self.inner_artifact_list[key] = item
        # self.compute._assign_dependents()

    def __len__(self):
        return len(self.inner_artifact_list)

    def append(self, value):
        self.inner_artifact_list.append(value)
        # self.compute._assign_dependents()

    def _inner_copy(
        self,
        building_stages: dict["cf.stage.Stage", "cf.stage.Stage"] = None,
        building_artifacts: dict["cf.artifact.Artifact", "cf.artifact.Artifact"] = None,
    ):
        if building_stages is None:
            building_stages = {}
        if building_artifacts is None:
            building_artifacts = {}

        if self.internal_id in building_artifacts.keys():
            return building_artifacts[self.internal_id]

        artifact = ArtifactList(self.name, self.inner_artifact_list)
        building_artifacts[self.internal_id] = artifact
        artifact.cacher = copy.deepcopy(self.cacher)
        artifact.hash_str = self.hash_str
        artifact.hash_debug = self.hash_debug
        if self.compute is not None:
            artifact.compute = self.compute._inner_copy(
                building_stages, building_artifacts
            )
            if not isinstance(artifact.compute.outputs, list):
                artifact.compute.outputs = artifact
            else:
                # if it's a list, this artifact was only one of multiple
                # outputs, so search through and replace just the one with the
                # same name
                for index, output in enumerate(artifact.compute.outputs):
                    # print("Changing multioutputs for stage", artifact.compute.name
                    if output.name == self.name:
                        artifact.compute.outputs[index] = artifact
        artifact.previous_context_names = [*self.previous_context_names]
        if (
            self.context is not None
            and self.context.name not in artifact.previous_context_names
            and (
                artifact.context is not None
                and artifact.context.name != self.context.name
            )
        ):
            # print("Adding", self.context.name)
            # print(artifact.context_name)
            artifact.previous_context_names.append(self.context.name)
        return artifact

    # TODO: define iterator?


# TODO: no I don't like this
# @stage.stage([Artifact("combined")])
def _aggregate_artifact_list(*input_artifacts):
    return [*input_artifacts]
