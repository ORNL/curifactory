import json
import os
import pickle
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from artifact import Artifact
from manager import Manager


class Cacheable:
    def __init__(self, path_override: str = None, extension: str = ""):
        self.path_override = path_override
        self.extension = extension
        self.artifact: Artifact = None
        self.extra_metadata: dict = None

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

        hash, _ = self.artifact.compute_hash()
        cache_path = Manager.get_manager().cache_path
        return str(Path(cache_path) / f"{hash}_{self.artifact.name}{self.extension}")

    def check(self):
        Manager.get_manager().logger.debug(
            f"Checking for cached {self.artifact.name} at '{self.get_path()}'"
        )
        return os.path.exists(self.get_path())

    def save_func(self, obj):
        pass

    def save(self, obj):
        self.save_func(obj)
        self.save_metadata()

    def save_metadata(self):
        metadata_path = self.get_path("_metadata.json")

        metadata = dict(
            cacher_type=str(type(self)), cacher_extra_metadata=self.extra_metadata
        )
        with open(metadata_path, "w") as outfile:
            json.dump(metadata, outfile, indent=2, default=str)

    def load_func(self):
        pass

    def load(self, obj):
        self.load_metadata()
        return self.load_func()

    def load_metadata(self):
        pass


class JsonCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".json")

    def save_func(self, obj):
        with open(self.get_path(), "w") as outfile:
            json.dump(obj, outfile)

    def load_func(self):
        with open(self.get_path()) as infile:
            obj = json.load(infile)
        return obj


class PickleCacher(Cacheable):
    def __init__(self, path_override: str = None):
        super().__init__(path_override, ".pkl")

    def save_func(self, obj):
        with open(self.get_path(), "wb") as outfile:
            pickle.dump(obj, outfile)

    def load_func(self):
        with open(self.get_path(), "rb") as infile:
            obj = pickle.load(infile)
        return obj


class ParquetCacher(Cacheable):
    pass


class DBTableCacher(Cacheable):
    def __init__(self, db_path_override: str = None, table_name: str = None):
        # TODO: table_name should default to artifact name
        super().__init__(db_path_override, extension="db")

    def check(self):
        # TODO:
        pass

    def save_func(
        self,
        obj: duckdb.DuckDBPyRelation
        | pd.DataFrame
        | dict[str, list]
        | list[dict[str | Any]],
    ):
        pass
        # if table already exists


class DBTableRelationVerifier(Cacheable):
    # assumes the user is in charge of all SQL queries, and simply returns a
    # relation of modified rows - this verifier hashes that and stores the hash
    # for future checks
    pass
