import json
import os
import pickle
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

import curifactory.experimental as cf
from curifactory.experimental.artifact import Artifact
from curifactory.experimental.manager import Manager


class Cacheable:
    def __init__(
        self, path_override: str = None, extension: str = "", paths_only: bool = False
    ):
        self.path_override = path_override
        self.extension = extension
        self.artifact: cf.artifact.Artifact = None
        self.extra_metadata: dict = None
        self.paths_only: bool = paths_only
        """When True, after the object is saved it is replaced with
        the string path it was saved at. Similarly, when load is called,
        the path gets returned."""

    def _resolve_suffix(
        self, path: str, suffix: str, add_extension: bool = True
    ) -> str:
        """Handles determining the final suffix of a path based on the extension of
        this cacheable and whether a specific suffix was requested or not."""

        # this is the logic to add an extension if no suffix supplied and the
        # object name/override path doesn't already contain the extension
        if suffix is None and (
            self.extension is not None
            and self.extension != ""
            and not path.endswith(self.extension)
            and add_extension
        ):
            suffix = self.extension
        elif suffix is None:
            suffix = ""

        return suffix

    def get_path(self, suffix=None) -> str:
        if self.path_override is not None:
            path = self.path_override
            # TODO: templating?

            # if the path_override has the extension in it already, remove it to handle
            # suffix addition consistently with non-path_override case
            # (the extension will be re-added in as necessary)
            # NOTE: we only do this if suffix is specified, otherwise we assume
            # path override is exactly what's desired. This is important because if
            # someone calls record.get_path and passes it in here, that get_path won't
            # auto handle an extension, and we need this get_path to return the same
            # thing as expected from record.get_path for tracking to work.
            if (
                self.extension != ""
                and self.extension is not None
                and path.endswith(self.extension)
                and suffix is not None
            ):
                path = path[: path.rindex(self.extension)]

            suffix = self._resolve_suffix(path, suffix, False)
            path = path + suffix
            return path
        else:
            suffix = self._resolve_suffix(self.artifact.name, suffix)
            name = self.artifact.name + suffix
            hash, _ = self.artifact.compute_hash()
            cache_path = cf.manager.Manager.get_manager().cache_path
            return str(Path(cache_path) / f"{hash}_{name}")
            # return str(Path(cache_path) / f"{hash}_{self.artifact.name}{self.extension}")

    def check(self):
        cf.manager.Manager.get_manager().logger.debug(
            f"Checking for cached {self.artifact.name} at '{self.get_path()}'"
        )
        return os.path.exists(self.get_path())

    def save_obj(self, obj):
        pass

    def save_metadata(self):
        metadata_path = self.get_path("_metadata.json")
        cf.manager.Manager.get_manager().logger.debug(
            f"Saving {self.artifact.name} metadata at '{metadata_path}'..."
        )
        metadata = dict(
            # cf_version=
            cacher_type=str(type(self)),
            cacher_extra_metadata=self.extra_metadata,
            artifact_id=self.artifact.db_id,
            artifact_hash=self.artifact.hash_str,
            paths=self.load_paths(),
            # stage_id=self.artifact.compute.db_id,
            # stage_params=self.artifact.compute.db_id,
        )
        with open(metadata_path, "w") as outfile:
            json.dump(metadata, outfile, indent=2, default=str)

    def save(self, obj):
        cf.manager.Manager.get_manager().logger.debug(
            f"Saving {self.artifact.name} at '{self.get_path()}'..."
        )
        self.save_obj(obj)
        self.save_metadata()
        if self.paths_only:
            self.artifact.obj = self.load_paths()

    def load_obj(self):
        pass

    def load_paths(self):
        return self.get_path()

    def load(self):
        self.load_metadata()
        if self.paths_only:
            return self.load_paths()
        return self.load_obj()

    def load_metadata(self):
        metadata_path = self.get_path("_metadata.json")
        with open(metadata_path) as infile:
            metadata = json.load(infile)

        self.extra_metadata = metadata["cacher_extra_metadata"]
        self.artifact.db_id = metadata["artifact_id"]
        # CANC: try to load from db?
        # if not cf.manager.Manager.get_manager().load_artifact_metadata_by_id(metadata["artifact_id"], self.artifact):
        #     pass

    def load_artifact(self, path: str) -> "cf.artifact.Artifact":
        # TODO:
        pass


class JsonCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".json")

    def save_obj(self, obj):
        with open(self.get_path(), "w") as outfile:
            json.dump(obj, outfile)

    def load_obj(self):
        with open(self.get_path()) as infile:
            obj = json.load(infile)
        return obj


class PickleCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".pkl")

    def save_obj(self, obj):
        with open(self.get_path(), "wb") as outfile:
            pickle.dump(obj, outfile)

    def load_obj(self):
        with open(self.get_path(), "rb") as infile:
            obj = pickle.load(infile)
        return obj


class ParquetCacher(Cacheable):
    def __init__(
        self,
        path_override: str = None,
        paths_only: bool = False,
        use_db_arg: int | str = -1,
    ):
        super().__init__(path_override, ".parquet", paths_only=paths_only)
        self.use_db_arg = use_db_arg

    def save_obj(
        self,
        obj: duckdb.DuckDBPyRelation
        | pd.DataFrame
        | dict[str, list]
        | list[dict[str | Any]],
    ):
        if isinstance(obj, duckdb.DuckDBPyRelation):
            # NOTE: this is necessary because unless db conn string info is
            # provided somehow, we have no db object with which to load the
            # parquet file.
            if self.use_db_arg == -1:
                self.paths_only = True
            obj.to_parquet(self.get_path())
            return

        if isinstance(obj, (list | dict)):
            obj = pd.DataFrame(obj)

        if isinstance(obj, pd.DataFrame):
            obj.to_parquet(self.get_path())
            return
        raise Exception(
            f"ParquetCacher unclear how to save object of type {type(obj)} for artifact {self.artifact.name}"
        )

    def load_obj(self):
        if self.use_db_arg == -1:
            return pd.read_parquet(self.get_path())
        else:
            args, kwargs = self.artifact.compute.resolve_args()
            if isinstance(self.use_db_arg, int):
                db = args[self.use_db_arg]
            elif isinstance(self.use_db_arg, str):
                db = kwargs[self.use_db_arg]
            else:
                raise TypeError(
                    "use_db_arg must either be an args index or kwargs kw string name"
                )
            return db.from_parquet(self.get_path())


class MetadataOnlyCacher(Cacheable):
    """Only writes out a metadata file, can be used for checking that a
    stage was completed/based on parameters. The underlying assumption is that the
    stage only mutated something in some way and has no specific object to retrieve."""

    def __init__(self, path_override: str = None):
        super().__init__(path_override, "")


# class DBTableCacher(Cacheable):
#     def __init__(self, db_path_override: str = None, table_name: str = None):
#         # TODO: table_name should default to artifact name
#         super().__init__(db_path_override, extension="db")
#
#     def check(self):
#         # TODO:
#         pass
#
#     def save_obj(self, obj: duckdb.DuckDBPyRelation | pd.DataFrame | dict[str, list] | list[dict[str | Any]]):
#         pass
#         # if table already exists
#
#
# class DBTableRelationVerifier(Cacheable):
#     # assumes the user is in charge of all SQL queries, and simply returns a
#     # relation of modified rows - this verifier hashes that and stores the hash
#     # for future checks
#     pass
