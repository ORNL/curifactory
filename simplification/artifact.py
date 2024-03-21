# from simplification.experiment import Experiment
# from simplification.stage import Stage
import copy
import inspect
import logging
from functools import partial

import experiment
import stage
from graphviz import Digraph


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

        self._compute: stage.Stage = None

        # previous context names means every time we copy an artifact into a
        # new context, we assign the
        self._previous_context_names: list[str] = []
        self._context: experiment.Experiment = None
        # self.context: ArtifactManager = None
        # self.original_context:
        # self.context_name: str = None

        self.context = self._find_context()
        self._add_to_context()

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

    def _find_context(self) -> experiment.Experiment:
        # TODO: check if context is none first?
        for frame in inspect.stack():
            if "self" in frame.frame.f_locals.keys() and isinstance(
                frame.frame.f_locals["self"], experiment.Experiment
            ):
                # print("FOUND THE EXPERIMENT")
                return frame.frame.f_locals["self"]
        return None

    def _add_to_context(self):
        """Add this artifact to the context experiment's artifact manager."""
        if self.context is None:
            Artifacts.artifacts.append(self)
        else:
            self.context.artifacts.artifacts.append(self)

    def compute_hash(self):
        if self.compute is None:
            return ""
        self.hash_str, self.hash_debug = self.compute.compute_hash()
        return self.hash_str, self.hash_debug

    def __setattr__(self, name: str, value):
        # pass a reference for this artifact to the cacher so it can access info
        # like the artifact name etc.
        if name == "cacher" and value is not None:
            value.artifact = self
        super().__setattr__(name, value)

    def __repr__(self):
        # TODO: think through better set of things to show
        string = f"Artifact '{self.name}'"
        if self.computed:
            string += f": {repr(self.obj)}"
        return string

    @property
    def context_name(self):
        current = "None"
        if self.context is not None:
            current = self.context.name
        if len(self.previous_context_names) > 0:
            current += f" ({','.join(self.previous_context_names)})"
        return current

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

    def copy(self):
        artifact = Artifact(self.name)
        artifact.cacher = copy.deepcopy(self.cacher)
        artifact.obj = self.obj
        artifact.hash_str = self.hash_str
        artifact.hash_debug = self.hash_debug
        if self.compute is not None:
            artifact.compute = self.compute.copy()  # TODO: still wrong I think
            artifact.compute.outputs = self
        artifact.previous_context_names = [*self.previous_context_names]
        # TODO: ... so we need a new compute though, because the output artifact
        # will now be wrong.

        # TODO: put current context name into previous contexts, then replace
        # context?
        if self.context is not None:
            artifact.previous_context_names.append(self.context.name)
        return artifact

    def artifact_tree(self):
        return self.compute._artifact_tree()

    def dependencies(self) -> list["Artifact"]:
        """Gets any input artifacts from the compute stage."""
        artifact_dependencies = []
        for arg in self.compute._combined_args():
            if isinstance(arg, Artifact):
                artifact_dependencies.append(arg)
        return artifact_dependencies

    def artifact_list(self, building_list: list = None):
        if building_list is None:
            building_list = []
        building_list.append(self)

        for arg in self.compute._combined_args():
            if isinstance(arg, Artifact) and arg not in building_list:
                building_list = arg.artifact_list(building_list)
                # building_list.append(arg)
            # if isinstance(arg, ArtifactList):
            #     for list_artifact in arg.artifacts:
            #         print(list_artifact)
            #         building_list = list_artifact.artifact_list(building_list)

        return building_list

    def artifact_list_debug(self):
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
        dot.node(
            name=str(self.internal_id),
            label=str(self.name + "\n" + self.context_name + "\n" + self.hash_str[:6]),
        )

    def _visualize(self, dot=None):
        if dot is None:
            dot = Digraph()

        self._inner_visualize(dot)
        return dot

    def _inner_visualize(self, g):
        self._node(g)

        for dependency in self.dependencies():
            g.edge(str(dependency.internal_id), str(self.internal_id))
            g = dependency._visualize(g)

        return g


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
        self.artifacts = artifacts
        self.compute = stage.Stage(
            function=_aggregate_artifact_list,
            args=self.artifacts,
            kwargs={},
            outputs=[Artifact(name=self.name)],
        )
        self.compute.outputs = self

    def __repr__(self):
        return f"ArtifactList('{self.name}', {repr(self.artifacts)})"

    def __getitem__(self, key):
        return self.artifacts[key]

    def __setitem__(self, key, item):
        self.artifacts[key] = item
        self.compute._assign_dependents()

    def __len__(self):
        return len(self.artifacts)

    def append(self, value):
        self.artifacts.append(value)
        self.compute._assign_dependents()

    # TODO: define iterator?


# TODO: no I don't like this
# @stage.stage([Artifact("combined")])
def _aggregate_artifact_list(*input_artifacts):
    return [*input_artifacts]
