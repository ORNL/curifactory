# from simplification.experiment import Experiment
# from simplification.stage import Stage
import copy
import inspect

import experiment
import stage
from graphviz import Digraph, Graph


class ArtifactManager:
    # TODO: possibly needs a name?
    def __init__(self):
        self.artifacts: dict[str, Artifact | ArtifactManager] = {}
        pass

    def __getitem__(self, key):
        return self.artifacts[key]

    # def __setitem__(self, key, value):
    #     pass

    def display(self):
        for key, value in self.artifacts.items():
            print(
                key.ljust(20), ":", repr(value).ljust(50), ":", str(id(value)).ljust(30)
            )


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
    def __init__(self, name=None, cacher=None):
        self.name = name
        self.cacher = cacher
        self.object = None

        self.computed: bool = False

        # TODO: these should probably be properties that just return the
        # compute stage's hash str
        self.hash_str = None
        self.hash_debug = None

        self.compute: stage.Stage = None

        self.context: experiment.Experiment = None
        # self.context: ArtifactManager = None
        # self.original_context:
        # self.context_name: str = None

        # print(inspect.getouterframes(inspect.currentframe())[1])
        # print(inspect.stack()[2])
        # TODO: perhaps a better way is to check each attribute for an
        # ArtifactManager type instead of assuming it has to come from an
        # experiment definition?
        # print("===========")
        # if name is not None:
        #     print("artifact:", name)
        # else:
        #     print("?")

        self.context = self._find_context()

        # the reason I'm hesitant to explicitly track dependents is that someone
        # could theoretically define a custom experiment dataclass and do weird
        # things like set one of the artifacts as a class variable, which
        # wouldn't be caught? Quite frankly that's such a ridiculous use case
        # though, that I don't think that's realistically going to be an issue.
        self.dependents: list[stage.Stage] = []
        # self.pointer = None

    def _find_context(self) -> experiment.Experiment:
        # TODO: check if context is none first?
        for frame in inspect.stack():
            if "self" in frame.frame.f_locals.keys() and isinstance(
                frame.frame.f_locals["self"], experiment.Experiment
            ):
                # print("FOUND THE EXPERIMENT")
                return frame.frame.f_locals["self"]
        return None

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
            string += f": {repr(self.object)}"
        return string

    # def replace(self, artifact):
    #     self.pointer = artifact
    def replace(self, artifact):
        # TODO: TODO: TODO: TODO: here is where we would copy the incoming
        # artifact if different context

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
        # self.pointer = artifact
        for stage in self.dependents:
            for i, arg in enumerate(stage.args):
                if arg == self:
                    stage.args[i] = artifact
            for key in stage.kwargs:
                if stage.kwargs[key] == self:
                    stage.kwargs[key] = artifact
            # if self in stage.args:
            #     stage.args.rep

        # when we replace an artifact, we only need to search _forward_ for
        # stage args to replace.

    def copy(self):
        artifact = Artifact(self.name)
        artifact.cacher = copy.deepcopy(self.cacher)
        artifact.object = self.object
        artifact.hash_str = self.hash_str
        artifact.hash_debug = self.hash_debug
        artifact.compute = self.compute
        # TODO: ... so we need a new compute though, because the output artifact
        # will now be wrong.
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
        dot.node(name=str(id(self)), label=str(self.name + "\n" + self.hash_str[:6]))

    def _visualize(self, dot=None):
        if dot is None:
            dot = Digraph()

        self._inner_visualize(dot)
        return dot

    def _inner_visualize(self, g):
        self._node(g)

        for dependency in self.dependencies():
            g.edge(str(id(dependency)), str(id(self)))
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
