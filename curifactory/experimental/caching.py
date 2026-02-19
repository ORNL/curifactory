import importlib
import json
import os
import pickle
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

import curifactory.experimental as cf


class Cacheable:
    params = ["path_override", "extension", "paths_only"]

    def __init__(
        self, path_override: str = None, extension: str = "", paths_only: bool = False
    ):
        self.path_override = path_override
        self.extension = extension
        self.artifact: cf.artifact.Artifact = None
        self.extra_metadata: dict = {}
        self.paths_only: bool = paths_only
        """When True, after the object is saved it is replaced with
        the string path it was saved at. Similarly, when load is called,
        the path gets returned."""

        self.cache_paths: list = []
        # self.cache_path: str = None
        # """If None, use the manager's cache path?"""

    def resolve_template_string(self, path: str) -> str:
        """Intended for when path_override is specified, this returns the path with
        formatting applied/resolved.

        Note that this does _not_ handle suffixing, suffix resolution needs to occur wherever
        this is used.

        Possible keyword replacement fields:
        * `{hash}` - the hash of the stage.
        * `{stage_name}` - the name of the stage that produces this artifact
        * `{[STAGE_ARG_NAME]}` - any argument name from the stage itself
        * `{artifact_name}` - the name of this output object.
        * `{artifact_filename}` - the normal filename for this cacher (doesn't include dir path etc.)
        """
        # * `{cache}` - the path to the manager's cache directory (does not include final '/')
        # * `{stage_arg_[INDEX]}`
        # TODO: some of this doesn't work if artifact is None
        format_dict = cf.utils.FailsafeDict()
        if self.artifact is not None:
            format_dict = cf.utils.FailsafeDict(
                artifact_name=self.artifact.name,
                artifact_filename=f"{self.artifact.compute_hash()[0]}_{self._resolve_suffix(self.artifact.name, None)}",
            )
            path = self.artifact.compute.resolve_template_string(path)
        path = path.format(**format_dict)
        return path

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

    def get_path(self, suffix=None, dry=False) -> str:
        """When dry is false don't add the resulting path to the cacher's list
        of tracked paths, (e.g. if this is just being used in a print statement.)"""
        if self.path_override is not None:
            path = self.path_override

            path = self.resolve_template_string(path)

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
            if not dry and path not in self.cache_paths:
                self.cache_paths.append(path)
            return path
        else:
            suffix = self._resolve_suffix(self.artifact.name, suffix)
            name = self.artifact.name + suffix
            hash, _ = self.artifact.compute_hash()
            cache_path = cf.manager.Manager.get_manager().cache_path
            full_path = str(Path(cache_path) / f"{hash}_{name}")
            if not dry and full_path not in self.cache_paths:
                self.cache_paths.append(full_path)
            return full_path

    def get_params(self) -> dict[str, Any]:
        params_dict = {}
        for param in self.params:
            params_dict[param] = getattr(self, param)
        return params_dict

    def check(self, silent: bool = False):
        if not silent:
            cf.manager.Manager.get_manager().logger.debug(
                f"Checking for cached {self.artifact.name} at '{self.get_path(dry=True)}'"
            )
        exists = os.path.exists(self.get_path(dry=True))
        if exists and not silent:
            cf.get_manager().logger.debug(f"Found {self.get_path(dry=True)}")
        return exists

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
            cacher_params=self.get_params(),
            artifact_id=self.artifact.db_id,
            artifact_hash=self.artifact.hash_str,
            paths=self.cache_paths,
            stage_id=(
                self.artifact.compute.db_id
                if self.artifact.compute is not None
                else None
            ),
            # stage_params=self.artifact.compute.db_id,
        )
        self.metadata = metadata
        with open(metadata_path, "w") as outfile:
            json.dump(metadata, outfile, indent=2, default=str)

    def save(self, obj):
        cf.manager.Manager.get_manager().logger.debug(
            f"Saving {self.artifact.name} at '{self.get_path(dry=True)}'..."
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
        cf.get_manager().logger.debug(
            f"Reloading {self.artifact.name} from '{self.get_path(dry=True)}'..."
        )
        self.load_metadata()
        if self.paths_only:
            return self.load_paths()
        obj = self.load_obj()
        if self.artifact is not None:
            cf.get_manager().logger.debug("setting object on artifact")
            self.artifact.obj = obj
        cf.get_manager().logger.debug(f"Completed loading {self.artifact.name}")
        return obj

    def load_metadata(self):
        metadata_path = self.get_path("_metadata.json")

        if not Path(metadata_path).exists():
            return {}

        with open(metadata_path) as infile:
            metadata = json.load(infile)

        self.extra_metadata = metadata["cacher_extra_metadata"]
        self.artifact.db_id = metadata["artifact_id"]
        self.cache_paths = metadata["paths"]
        # CANC: try to load from db?
        # if not cf.manager.Manager.get_manager().load_artifact_metadata_by_id(metadata["artifact_id"], self.artifact):
        #     pass
        return metadata

    def load_artifact(self, path: str) -> "cf.artifact.Artifact":
        # TODO:
        pass

    def clear(self):
        """Remove self from the cache."""
        cf.get_manager().logger.debug(f"Removing {self.artifact.name} from cache")
        self.load_metadata()
        self.clear_obj()
        self.clear_metadata()

    def clear_obj(self):
        paths = self.cache_paths
        # if isinstance(paths, str):
        #     cf.get_manager().logger.debug(f"\tClearing {paths}")
        #     Path(paths).unlink(missing_ok=True)
        # if isinstance(paths, list):
        for path in paths:
            cf.get_manager().logger.debug(f"\tClearing {path}")
            Path(path).unlink(missing_ok=True)

    def clear_metadata(self):
        Path(self.get_path("_metadata.json")).unlink(missing_ok=True)

    @staticmethod
    def get_from_db_metadata(
        cacher_module: str, cacher_type: str, cacher_params: dict[str, Any]
    ):
        cf.get_manager().logger.debug(
            f"Instantiating cacher from module '{cacher_module}' of type '{cacher_type}' with params {cacher_params}"
        )
        module = importlib.import_module(cacher_module)
        cacher_class = getattr(module, cacher_type)
        print(type(cacher_params), cacher_params)
        return cacher_class(**cacher_params)


class JsonCacher(Cacheable):
    params = ["path_override"]

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
    params = ["path_override"]

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
    params = ["path_override", "paths_only", "use_db_arg"]

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
        obj: (
            duckdb.DuckDBPyRelation
            | pd.DataFrame
            | dict[str, list]
            | list[dict[str | Any]]
        ),
    ):
        # if self.use_db_arg != -1:
        #     """If told to use db, convert to relation"""
        #     obj =
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
            if isinstance(self.use_db_arg, int):
                db = self.artifact.compute.resolve_arg(False, arg_index=self.use_db_arg)
            elif isinstance(self.use_db_arg, str):
                db = self.artifact.compute.resolve_arg(False, arg_name=self.use_db_arg)
            else:
                raise TypeError(
                    "use_db_arg must either be an args index or kwargs kw string name"
                )

            return db.from_parquet(self.get_path())


class DBCacher(Cacheable):
    """A cacher that loads a duckdb database connection."""

    params = ["connection_str", "kwargs", "extensions"]

    def __init__(
        self, connection_str: str = None, extensions: list[str] = None, **kwargs
    ):
        super().__init__(extension=".db")
        self.connection_str = connection_str
        self.extensions = extensions
        self.kwargs = kwargs

        if self.extensions is None:
            self.extensions = []

    def check(self, silent: bool = False):
        return True

    def load(self):
        # modified to change log language and also both load/save metadata
        self.load_metadata()
        obj = self.load_obj()
        if self.artifact is not None:
            cf.get_manager().logger.debug("setting object on artifact")
            self.artifact.obj = obj
            cf.get_manager().record_artifact(self.artifact)
            self.artifact.computed = True
        cf.get_manager().logger.debug(f"Completed loading {self.artifact.name}")
        self.save_metadata()
        return obj

    def load_obj(self):
        if self.connection_str is None:
            self.connection_str = self.get_path()
        cf.get_manager().logger.info(f"Loading db at {self.connection_str}...")
        db = duckdb.connect(self.connection_str)
        for extension in self.extensions:
            try:
                db.load_extension(extension)
                cf.get_manager().logger.debug(f"Loaded db extension {extension}")
            except duckdb.IOException:
                try:
                    cf.get_manager().logger.debug(
                        f"Trying to install extension {extension}..."
                    )
                    db.install_extension(extension)
                except duckdb.HTTPException:
                    cf.get_manager().logger.debug(
                        f"Trying to install community extension {extension}..."
                    )
                    db.install_extension(extension, repository="community")
                db.load_extension(extension)
                cf.get_manager().logger.debug(f"Loaded db extension {extension}")
        return db


class DBTableCacher(Cacheable):
    params = ["path_override", "use_db_arg", "table_name"]

    # NOTE: returns _the entire table that gets saved into_
    def __init__(
        self,
        path_override: str = None,
        use_db_arg: int | str = -1,
        table_name: str = None,
        db: duckdb.DuckDBPyConnection = None,
    ):
        # TODO: would be nice if use_db_arg expected template string same as
        # table_name?
        super().__init__(path_override, "")
        self.use_db_arg = use_db_arg
        self.table_name = table_name
        self.db = db

    def get_db(self):
        if self.db is not None:
            return self.db
        if self.path_override is not None:
            # TODO: load db
            pass
        else:
            if isinstance(self.use_db_arg, int):
                db = self.artifact.compute.resolve_arg(False, arg_index=self.use_db_arg)
            elif isinstance(self.use_db_arg, str):
                db = self.artifact.compute.resolve_arg(False, arg_name=self.use_db_arg)
            else:
                raise TypeError(
                    "use_db_arg must either be an args index or kwargs kw string name"
                )
            return db

    def get_table_name(self):
        if self.table_name is None:
            return self.artifact.name
        return self.resolve_template_string(self.table_name)

    def upsert_relation(self, relation_object: duckdb.DuckDBPyRelation):
        db = self.get_db()
        try:
            db.sql(
                f"CREATE TABLE {self.get_table_name()} AS SELECT * FROM relation_object"
            )
            self.extra_metadata["result"] = "created"
        except duckdb.CatalogException:
            db.sql(
                f"INSERT OR REPLACE INTO {self.get_table_name()} (SELECT * FROM relation_object)"
            )
            self.extra_metadata["result"] = "updated"
            cf.get_manager().logger.debug(
                f"Inserting relation to pre-existing table {self.get_table_name()}"
            )

    # TODO: probably need better upsert logic
    # TODO: should use db in a context manager if not use_db_arg?
    def save_obj(self, relation_object: duckdb.DuckDBPyRelation):
        db = self.get_db()
        self.upsert_relation(relation_object)
        if self.artifact is not None:
            self.artifact.obj = db.sql(f"SELECT * FROM {self.get_table_name()}")

    def load_obj(self):
        db = self.get_db()
        return db.sql(f"SELECT * FROM {self.get_table_name()}")

    def check(self, silent=True):
        if not Path(self.get_path("_metadata.json", dry=True)).exists():
            return False
        # TODO: should we also check for the table?
        return True


# TODO: terrible name, figure out better one (maybe call this one dbtablecacher
# and the base NonTrackingDBTableCacher)
class TrackingDBTableCacher(DBTableCacher):
    params = ["path_override", "use_db_arg", "table_name", "id_cols"]

    def __init__(
        self,
        path_override: str = None,
        use_db_arg: int | str = -1,
        table_name: str = None,
        db: duckdb.DuckDBPyConnection = None,
        id_cols: dict[str, str] = None,  # have to include type unfortunately
    ):
        super().__init__(path_override, use_db_arg, table_name, db)
        self.id_cols = id_cols
        if id_cols is None:
            raise Exception(
                "TrackingDBTableCacher must be provided with a set of columns to uniquely ID each row."
            )

    def save_obj(self, relation_object: duckdb.DuckDBPyRelation):

        id_column_type_list = ",".join(
            [id_col + " " + self.id_cols[id_col] for id_col in self.id_cols]
        )
        id_column_list = ",".join([id_col for id_col in self.id_cols])

        db = self.get_db()
        db.sql(
            f"CREATE TABLE IF NOT EXISTS _cftrack_{self.get_table_name()} ({id_column_type_list}, metadata_id UUID)"
        )

        self.clear_obj()

        # insert the relation into normal table
        self.upsert_relation(relation_object)

        # ensure primary keys
        if self.extra_metadata["result"] == "created":
            query = f"ALTER TABLE {self.get_table_name()} ADD PRIMARY KEY ({id_column_list})"
            try:
                db.sql(query)
            except duckdb.duckdb.ParserException as e:
                if sys.version_info >= (3, 11, 0):
                    e.add_note(f"Was trying to run query: {query}")
                raise

        # add a metadata row
        stage_id = self.artifact.compute.db_id
        # db.execute("INSERT INTO _cf_metadata VALUES (?, ?)", [stage_id, self.get_table_name()])

        # Add a row for each row in relation_object
        tracking_rows = db.sql(  # noqa: F841
            f"SELECT {id_column_list}, '{stage_id}' as metadata_id from relation_object"
        )
        db.sql(
            f"INSERT INTO _cftrack_{self.get_table_name()} (SELECT * FROM tracking_rows)"
        )

    def equals_condition(self, prefix):
        condition = " AND ".join(
            [
                f"{self.get_table_name()}.{id_col} = {prefix}.{id_col}"
                for id_col in self.id_cols
            ]
        )
        return condition

    def join_condition(self):
        metadata = self.load_metadata()
        stage_id = metadata["stage_id"]
        condition = self.equals_condition(f"_cftrack_{self.get_table_name()}")
        # condition = " AND ".join([f"{self.get_table_name()}.{id_col} = _cftrack_{self.get_table_name()}.{id_col}" for id_col in self.id_cols])
        condition += f" AND _cftrack_{self.get_table_name()}.metadata_id = '{stage_id}'"
        return condition

    # TODO: clear function
    def clear_obj(self):
        metadata = self.load_metadata()
        if len(metadata) == 0:
            return
        stage_id = metadata["stage_id"]

        db = self.get_db()
        try:
            deletion_query = f"DELETE FROM {self.get_table_name()} USING ({self.get_table_name()} INNER JOIN _cftrack_{self.get_table_name()} ON {self.join_condition()}) AS delete_ref WHERE {self.equals_condition('delete_ref')}"
            db.sql(deletion_query)
        except Exception as e:
            cf.get_manager().logger.warning(f"Unable to clear {self.get_table_name()}: e")
            cf.get_manager().logger.debug(f"Was running query: {deletion_query}")
            return
            # if sys.version_info >= (3, 11, 0):
            #     e.add_note(f"Was running query: {deletion_query}")
            # raise

        db.sql(
            f"DELETE FROM _cftrack_{self.get_table_name()} WHERE metadata_id = '{stage_id}'"
        )

    def load_obj(self):
        db = self.get_db()
        selection_query = f"SELECT {self.get_table_name()}.* FROM {self.get_table_name()} INNER JOIN _cftrack_{self.get_table_name()} ON {self.join_condition()}"
        try:
            return db.sql(selection_query)
        except Exception as e:
            if sys.version_info >= (3, 11, 0):
                e.add_note(f"Was running selection query: {selection_query}")
            raise


class MetadataOnlyCacher(Cacheable):
    """Only writes out a metadata file, can be used for checking that a
    stage was completed/based on parameters. The underlying assumption is that the
    stage only mutated something in some way and has no specific object to retrieve."""

    params = ["path_override"]

    def __init__(self, path_override: str = None):
        super().__init__(path_override)

    def check(self, silent=False):
        if not Path(self.get_path("_metadata.json", dry=True)).exists():
            return False
        return True

    # TODO: doesn't this only need to check metadata file instead/ think this
    # needs to implement check


class AggregateArtifactCacher(Cacheable):
    """Just meant to help avoid unwanted implicit _aggregate stages continually
    being added to the database when nothing is _really_ running.

    NOTE: Can't be used as an inline cacher? (depends on an initialized
    ArtifactList artifact)
    """

    params = []

    def __init__(self):
        super().__init__()

    def check(self, silent=True):
        if not Path(self.get_path("_metadata.json", dry=True)).exists():
            return False
        for artifact in self.artifact.inner_artifact_list:
            if artifact.cacher is None:
                return False
            # if not artifact.cacher.check(silent=True):
            if not artifact.cacher.check():
                return False
        return True

    def load_obj(self):
        objs = []
        for artifact in self.artifact.inner_artifact_list:
            obj = artifact.get()
            objs.append(obj)
        return objs


class PathRef(Cacheable):
    """Special type of cacher that doesn't directly save or load anything, it just tracks a file path
    for reference.

    This is primarily useful for stages that never keep a particular object in memory and just want to
    directly pass around paths. The ``PathRef`` cacher allows still short-circuiting if the referenced
    path already exists, rather than needing to do it manually in the stage.

    Note that when using a ``PathRef`` cacher you still need to return a value from the stage for the
    cacher to "save". This cacher expects that return value to be the path that was written to, and
    internally runs an ``assert returned_path == self.get_path()`` to double check that the stage wrote
    to the correct place. This also means that the value stored "in memory" is just the path, and that
    path string is what gets gets "loaded".

    This cacher is distinct from the ``FileReferenceCacher`` in that the path of this cacher _is the
    referenced path_, rather than saving a file that contains the referenced path. (In the case of the
    latter, a new record/hash etc that refers to the same target filepath would still trigger stage
    execution and still requires the stage to do it's own check of if the original file already exists
    before saving.

    Example:

        .. code-block:: python

            @stage([], ["large_dataset_path"], [PathRef("./data/raw/big_data_{params.dataset}.csv")])
            def make_big_data(record):
                # you can use record's ``stage_cachers`` to get the expected path
                output_path = record.stage_cachers[0].get_path()
                ...
                # make big data without keeping it in memory
                ...
                return output_path

        .. code-block:: python

            @stage(["large_dataset_path"], ["model_path"], [PathRef])
            def make_big_data(record, large_dataset_path):
                # the other way you can get a path that should be correct
                # is through record's ``get_path()``. The assert inside
                # PathRef's save will help us double check that it's correct.
                output_path = record.get_path(obj_name="model_path")
                ...
                # train model using large_dataset_path, the string path we need.
                ...
                return output_path
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, obj: str):
        """This is effectively a no-op, this cacher is just a reference to its own path.
        ``obj`` is expected to be the same, and we assert that to help alert the user if
        something got mis-aligned and the path they wrote to wasn't this cacher's path.
        """
        internal_path = self.get_path()
        assert (
            internal_path == obj
        ), f"Stage returned unexpected path to PathRef cacher for artifact '{self.name}':\n\tExpected: '{internal_path}'\n\tReturned: '{obj}'"
        return internal_path

    def load(self) -> str:
        return self.get_path()


class FileReferenceCacher(Cacheable):
    """Saves a file path or list of file paths generated from a stage as a json file.
    The ``check`` function will check existence of all file paths.

    This is useful for instances where there may be a large number of files stored or
    generated to disk, as it would be unwieldy to return them all (or infeasible to keep them
    in memory) directly from the stage. When this cacher is checked for pre-existing,
    it tries to load the json file storing the filenames, and then checks for the existence of
    each path in that json file. If all of them exist, it will short-circuit computation.

    Using this cacher does mean the user is in charge of loading/saving the file paths correctly,
    but in some cases that may be desirable.

    This can also be used for storing a reference to a single file outside the normal cache.

    When combined with the ``get_dir`` call on the record, you can create a cached directory of
    files similarly to a regular cacher and simply keep a reference to them as part of the actual
    cacher process.

    Example:

        .. code-block:: python

            @stage(inputs=None, outputs=["many_text_files"], cachers=[FileReferenceCacher])
            def output_text_files(record):
                file_path = record.get_dir("my_files")
                my_file_list = [os.path.join(file_path, f"my_file_{num}") for num in range(20)]

                for file in my_file_list:
                    with open(file, 'w') as outfile:
                        outfile.write("test")

                return my_file_list
    """

    params = ["path_override"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, extension=".json", **kwargs)

    def check(self, silent: bool = False) -> bool:
        # check the file list file exists
        if not super().check(silent):
            return False

        # load the file list and check each file
        # NOTE: we don't need to re-check args overwrite because that
        # would already have applied in the super check
        with open(self.get_path()) as infile:
            files = json.load(infile)

        if isinstance(files, list):
            for file in files:
                cf.get_manager().logger.debug("Checking from file list: '%s'" % file)
                if not os.path.exists(file):
                    return False
        else:
            if not os.path.exists(files):
                return False

        return True

    def load_obj(self) -> list[str] | str:
        with open(self.get_path()) as infile:
            files = json.load(infile)
        return files

    # TODO: ??
    # def load_paths(self):
    #     return

    def save_obj(self, files: list[str] | str) -> str:
        path = self.get_path()
        with open(path, "w") as outfile:
            json.dump(files, outfile, indent=4)
        return path


class ReportablesCacher(FileReferenceCacher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = None

    def save_obj(self, reportables_list: list["cf.reporting.Reportable"]):
        paths = []
        for i, reportable in enumerate(reportables_list):
            name = reportable.name if reportable.name is not None else str(i)
            path = self.get_path(f"_{name}.pkl")
            PickleCacher(path).save_obj(reportable)
            paths.append(path)
        super().save_obj(paths)

    def load_obj(self) -> list["cf.reporting.Reportable"]:
        reportables = []
        paths = super().load_obj()
        for path in paths:
            reportables.append(PickleCacher(path).load_obj())
            reportables[-1].artifact = self.artifact
        return reportables


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
