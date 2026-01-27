# from simplification.experiment import Experiment
# from simplification.stage import Stage
import copy
import hashlib
import inspect
import json
import logging
from functools import partial
from typing import Any
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
    cache_status = pointer_based_property("cache_status")
    map_status = pointer_based_property("map_status")

    def __init__(self, name=None, cacher=None):
        self.pointer = None

        self._internal_id = id(self)

        self._name = name
        self._cacher = cacher
        self._obj = None

        self._computed: bool = False

        # TODO: these should probably be properties that just return the
        # compute stage's hash str
        # self._hash_str = None
        # self._hash_debug = None
        self.__hash_str = None
        self.__hash_debug = None

        self._compute: cf.stage.Stage = None

        # previous context names means every time we copy an artifact into a
        # new context, we assign the
        self._previous_context_names: list[str] = []
        self._context: cf.pipeline.Pipeline = None
        # self.context: ArtifactManager = None
        # self.original_context:
        # self.context_name: str = None

        self.context = self._find_context()
        self._add_to_context()

        self._db_id: UUID = None
        self._generated_time = None
        self._reportable: bool = False

        self._overwrite: bool = False

        self._map_status: int = None

        # the reason I'm hesitant to explicitly track dependents is that someone
        # could theoretically define a custom pipeline dataclass and do weird
        # things like set one of the artifacts as a class variable, which
        # wouldn't be caught? Quite frankly that's such a ridiculous use case
        # though, that I don't think that's realistically going to be an issue.
        # TODO: the better way to do this once artifacts are auto-added to the
        # context's artifactmanager might be to just check args of compute stage
        # of every artifact in the manager
        # self.dependents: list[stage.Stage] = []

    def __eq__(self, o):
        if o is None:
            return False
        if not isinstance(o, Artifact):
            return False
        return self.internal_id == o.internal_id

    # TODO: do we actually need to add every context on the stack?
    def _find_context(self) -> "cf.pipeline.Pipeline":
        # print("Seeking context for artifact ", self.name, cf.get_manager()._pipeline_defining_stack)
        if len(cf.get_manager()._pipeline_defining_stack) > 0:
            # self.context = cf.get_manager()._pipeline_defining_stack[-1]
            return cf.get_manager()._pipeline_defining_stack[-1]
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

    # TODO: if pipeline.artifacts is just filter of outputs, we may not
    # actually need this at all
    def _add_to_context(self):
        """Add this artifact to the context pipeline's artifact manager."""
        # if self.context is None:
        #     Artifacts.artifacts.append(self)
        # else:
        #     self.context.artifacts.artifacts.append(self)
        pass

    def compute_hash(self):
        if self.compute is None:
            return "", {}
        return self.compute.compute_hash()
        # self.hash_str, self.hash_debug = self.compute.compute_hash()
        # return self.hash_str, self.hash_debug

    def check_shared_artifact(self, other_artifact):
        """Two artifacts are considered equivalent (can be shared) if their hash and name is the same"""
        # TODO: is it a problem to use hash_str directly instead of compute_hash?
        if self.hash_str is None:
            logging.warning(
                f"Hash string of None on artifact {self.contextualized_name}"
            )
        if other_artifact.hash_str is None:
            logging.warning(
                f"Hash string of None on artifact {other_artifact.contextualized_name}"
            )
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

    # def check_cache(self):
    #     if self.cacher is not None:
    #         if self.cacher.check(silent=True):
    #             return True
    #     return False

    def reset_map(self):
        self.map_status = None
        self.cache_status = None
        self.compute.reset_map()

    def map(self, mapped: dict = None, need: bool = True, source=None):
        if mapped is None:
            self.reset_map()
            mapped = {"artifacts": [], "stages": [], "map": {}}

        if source is not None:
            map_name = f"{source.name} -> {self.name}"
        else:
            map_name = f"-> {self.name}"
        if self.name not in mapped["map"]:
            mapped["map"][self.name] = {}
        if map_name not in mapped["map"][self.name]:
            mapped["map"][self.name][map_name] = []

        if self not in mapped["artifacts"]:
            mapped["artifacts"].insert(0, self)

            # determine cache status
            if self.cacher is None:
                self.cache_status = cf.NO_CACHER
            else:
                if self.cacher.check(silent=True):
                    self.cache_status = cf.IN_CACHE
                else:
                    self.cache_status = cf.NOT_IN_CACHE

        # case priority:
        # 1. overwrite (force compute)
        # 2. in cache, so use it (the stage map will override this if something
        #   else required the compute to run)
        # 3. Not in cache and we need it so compute it
        # 4. Not needed!

        if self.determine_overwrite():
            self.map_status = cf.OVERWRITE
            mapped["map"][self.name][map_name].append(cf.OVERWRITE)
        else:
            if need and self.cache_status == cf.IN_CACHE:
                self.map_status = cf.USE_CACHE
                mapped["map"][self.name][map_name].append(cf.USE_CACHE)
            elif need:
                self.map_status = cf.COMPUTE
                mapped["map"][self.name][map_name].append(cf.COMPUTE)
            elif self.map_status is None:
                # we throw in the none check because we don't want to override
                # anything already set (if we run map on an artifact again)
                self.map_status = cf.SKIP
                mapped["map"][self.name][map_name].append(cf.SKIP)

        # if this mapping was requested from the compute (likely due to another
        # output of that stage), don't get stuck in a recurisve loop, just
        # return
        if self.compute == source:
            return mapped

        # recurse down into the stage map
        if self.map_status in [cf.COMPUTE, cf.OVERWRITE]:
            mapped = self.compute.map(mapped, need=True, source=self)
        else:
            mapped = self.compute.map(mapped, need=False, source=self)

        return mapped

    def get(self):
        cf.get_manager().logger.debug(
            f"Looking for artifact {self.contextualized_name} - {self.hash_str}"
        )
        try:
            # Note that computed is set by the _stage_
            if self.computed or self.obj is not None:
                cf.get_manager().logger.debug(f"\tAlready computed!")
                return self.obj
            overwrite = self.determine_overwrite()
            if self.cacher is not None and not overwrite:
                cf.get_manager().logger.debug(f"\tChecking cacher")
                if self.cacher.check():
                    self.obj = self.cacher.load()
                    # TODO: metadata stuff
                    return self.obj
                cf.get_manager().logger.debug("\tNot found in cache")

            # if this artifact is requested and no current target, that means
            # this is the target if a new run has to start
            manager = cf.get_manager()
            if manager.current_pipeline_run_target is None:
                manager.current_pipeline_run_target = self
            # (we handle associating the ID with the pipeline run during
            # record_artifact)

            if overwrite:
                manager.logger.info(f"Will overwrite artifact {self.name}")

            manager.logger.debug(
                f"\tPassing off to compute stage - {self.compute.name}"
            )
            self.compute()
            manager.logger.debug(
                f"\tReturning from compute stage {self.compute.name} to artifact {self.contextualized_name}"
            )
            # NOTE: stage handles running cachers
            return self.obj
        except Exception as e:
            e.add_note(f"Was trying to retrieve artifact {self.name}")
            raise

    @property
    def context_name(self):
        current = "None"
        if self.context is not None:
            current = f"({','.join([self.context.name] + self.previous_context_names)})"
        #     current = self.context.name
        # if len(self.previous_context_names) > 0:
        #     current += f"({','.join(self.previous_context_names)})"
        return current

    @property
    def contextualized_name(self):
        return f"{self.context_name}.{self.name}"

    def context_names_minus(self, minus: str):
        context_names = []
        if self.context is not None:
            context_names.append(self.context.name)
        context_names.extend(self.previous_context_names)
        if minus in context_names:
            context_names.remove(minus)
        return context_names

    @property
    def _hash_str(self):
        return self.compute_hash()[0]

    @property
    def _hash_debug(self):
        return self.compute_hash()[1]

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
        # artifact.hash_str = self.hash_str
        # artifact.hash_debug = self.hash_debug
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

    @staticmethod
    def load_from_uuid(
        uuid, building_stages: dict = None, building_artifacts: dict = None
    ):
        """Recurisvely load the full DAG prior to this artifact and then return this artifact."""
        if building_stages is None:
            building_stages = {}
        if building_artifacts is None:
            building_artifacts = {}

        if uuid in building_artifacts:
            return building_artifacts[uuid]

        with cf.get_manager().db_connection() as db:
            artifact_row = (
                db.sql(f"select * from cf_artifact where id = '{uuid}'").df().iloc[0]
            )

        prepopulated_stage = None
        if artifact_row.is_list:
            artifact = cf.artifact.ArtifactList(name=artifact_row["name"])
            prepopulated_stage = artifact.compute
        else:
            artifact = cf.artifact.Artifact(name=artifact_row["name"])
            # artifact.hash_str = artifact_row.hash
        artifact.db_id = uuid

        if artifact_row.cacher_type is not None:
            cacher_params = (
                json.loads(artifact_row.cacher_params)
                if artifact_row.cacher_params is not None
                else {}
            )
            cacher = cf.caching.Cacheable.get_from_db_metadata(
                artifact_row.cacher_module, artifact_row.cacher_type, cacher_params
            )
            artifact.cacher = cacher

        if not pd.isna(artifact_row.stage_id):
            stage = cf.stage.Stage.load_from_uuid(
                artifact_row.stage_id,
                building_stages,
                building_artifacts,
                prepopulated_stage=prepopulated_stage,
            )

            if artifact_row.is_list:
                artifact.inner_artifact_list = stage.args
            else:
                stage.outputs.append(artifact)
                artifact.compute = stage

        building_artifacts[uuid] = artifact

        return artifact

    def verify(self):
        if self.compute is None:
            return True
        if isinstance(self.compute.outputs, list):
            return self in self.compute.outputs
        return self == self.compute.outputs

    def artifact_tree(self):
        return self.compute._artifact_tree()

    def dependencies(self) -> list["Artifact"]:
        """Gets any input artifacts from the compute stage."""
        artifact_dependencies = []
        if self.compute is not None:
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

    def _node(self, dot, **kwargs):
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

        # context_names = ",".join(self.previous_context_names)
        context_names = self.context_name
        if "leave_out_context" in kwargs:
            context_names = ",".join(
                self.context_names_minus(kwargs["leave_out_context"])
            )

        style = None
        fillcolor = None
        if "color" in kwargs and kwargs["color"] == "cache":
            cache_status = self.cacher is not None and self.cacher.check(silent=True)
            style = "filled"
            if cache_status:
                fillcolor = "#AAFFAA"
            else:
                fillcolor = "#FFAAAA"
            if self.cacher is None:
                fillcolor = "#EEEEEE"

        dot.node(
            name=str(self.internal_id),
            label=str_name,
            shape="box",
            fontsize="8.0",
            height=".25",
            # xlabel=self.context_name,
            xlabel=context_names,
            style=style,
            fillcolor=fillcolor,
        )

    def visualize(self, g=None, **kwargs):
        if g is None:
            g = cf.utils.init_graphviz_graph()

        self._node(g, **kwargs)

        if self.compute is not None:
            self.compute.visualize(g, **kwargs)
            if (str(id(self.compute)), str(self.internal_id)) not in g._edges:
                g.edge(str(id(self.compute)), str(self.internal_id))
                g._edges.append((str(id(self.compute)), str(self.internal_id)))

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

        new_artifact_list = []
        for old_inner_artifact in self.inner_artifact_list:
            new_inner_artifact = old_inner_artifact._inner_copy(
                building_stages, building_artifacts
            )
            new_artifact_list.append(new_inner_artifact)
            # artifact.append(new_inner_artifact)
        artifact = ArtifactList(
            self.name, new_artifact_list
        )  # , self.inner_artifact_list)
        building_artifacts[self.internal_id] = artifact
        # artifact.cacher = copy.deepcopy(self.cacher)
        # artifact.hash_str = self.hash_str
        # artifact.hash_debug = self.hash_debug
        # if self.compute is not None:
        #     artifact.compute = self.compute._inner_copy(
        #         building_stages, building_artifacts
        #     )
        artifact.previous_context_names = [*self.previous_context_names]
        if (
            self.context is not None
            and self.context.name not in artifact.previous_context_names
            and (
                artifact.context is not None
                and artifact.context.name != self.context.name
            )
        ):
            # print(artifact.context_name)
            artifact.previous_context_names.append(self.context.name)
        return artifact

    # TODO: define iterator?


# TODO: no I don't like this
# @stage.stage([Artifact("combined")])
def _aggregate_artifact_list(*input_artifacts):
    return [*input_artifacts]


class StageReportables(Artifact):
    def __init__(self):
        super().__init__(name="reportables", cacher=cf.caching.ReportablesCacher())
        # apparently a cacher used in the init doesn't trigger the set_attr??
        self.cacher.artifact = self


class DBArtifact(Artifact):
    """Artifact that represents a duckdb connection"""

    def __init__(self, name: str = None, connection_str: str = None, **kwargs):
        super().__init__(
            name=name, cacher=cf.caching.DBCacher(connection_str, **kwargs)
        )
        self.cacher.artifact = self

    def compute_hash(self):
        # do an informal hash on the cacher params
        cacher_params = self.cacher.get_params()
        hash_values = {}
        for param, value in cacher_params.items():
            hash_values[param] = repr(value)
        hash_total = 0
        for key, value in hash_values.items():
            if value is None:
                continue
            hash_hex = hashlib.md5(f"{key}{value}".encode()).hexdigest()
            hash_total += int(hash_hex, 16)
        hash_str = f"{hash_total:x}"
        # self.hash_str = hash_str
        # self.hash_debug = hash_values
        return hash_str, hash_values
