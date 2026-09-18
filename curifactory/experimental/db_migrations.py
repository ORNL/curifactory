# NOTE: obviously, do not modify _original_schemas.
# In theory you should be able to have a database created with
# these original schemas, and then running all migrations would
# get you to an equivalent set of schemas to SCHEMAS in db_tables.
_original_schemas = {
    "cf_run": [
        "id UUID",
        "reference VARCHAR",
        "pipeline_class VARCHAR",
        "pipeline_name VARCHAR",
        "run_number INTEGER",
        "start_time TIMESTAMP",
        "end_time TIMESTAMP",
        "succeeded BOOL",
        "commit VARCHAR",
        "dirty BOOL",
        "hostname VARCHAR",
        "user VARCHAR",
        "notes VARCHAR",
        "hash VARCHAR",
        "params JSON",
        "target_id UUID",
    ],
    "cf_stage": [
        "id UUID",
        "run_id UUID",
        "func_name VARCHAR",
        "start_time TIMESTAMP",
        "end_time TIMESTAMP",
        "params JSON",
        "hash VARCHAR",
        "hash_details JSON",
        "func_module VARCHAR",
        "docstring VARCHAR",
    ],
    "cf_artifact": [
        "id UUID",
        "stage_id UUID",
        "run_id UUID",
        "name VARCHAR",
        "hash VARCHAR",
        "generated_time TIMESTAMP",
        "artifact_type VARCHAR",
        "cacher_type VARCHAR",
        "cacher_module VARCHAR",
        "cacher_params JSON",
        "reportable BOOL",
        "extra_metadata JSON",
        "repr VARCHAR",
        "is_list BOOL",
    ],
    "cf_run_stage": [
        "run_id UUID",
        "stage_id UUID",
    ],
    "cf_stage_input": [
        "stage_id UUID",
        "artifact_id UUID",
        "arg_index INTEGER",
        "arg_name VARCHAR",
        "stage_dependency_id UUID",
    ],
    "cf_run_artifact": [
        "run_id UUID",
        "artifact_id UUID",
    ],
    "cf_meta": ["schema_version INTEGER"],
}


def original_tables(db):
    for table, cols in _original_schemas.items():
        cols_str = ",\n".join(cols)
        db.sql(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                {cols_str}
            );
        """
        )
    db.sql("INSERT INTO cf_meta (schema_version) VALUES (1);")


def migration_20260210(db):
    """Add columns to the run table to record exception information, so they can
    be added to reports etc."""
    db.sql(
        """
        ALTER TABLE cf_run
        ADD COLUMN exception VARCHAR;

        ALTER TABLE cf_run
        ADD COLUMN exception_stack VARCHAR;

        INSERT INTO cf_meta (schema_version) VALUES (20260210);
    """
    )


def migration_20260829(db):
    """Add columns to track a bunch of run environment information, e.g. the git
    status, pip/conda packages, etc.."""
    db.sql(
        """
        ALTER TABLE cf_run
        ADD COLUMN host_env JSON;

        ALTER TABLE cf_run
        ADD COLUMN conda_env VARCHAR;

        ALTER TABLE cf_run
        ADD COLUMN pip_env VARCHAR;

        ALTER TABLE cf_run
        ADD COLUMN git_diff VARCHAR;

        ALTER TABLE cf_run
        ADD COLUMN cli VARCHAR;

        INSERT INTO cf_meta (schema_version) VALUES (20260829);
    """
    )


def migration_20260914(db):
    """Add a column to track any global config settings, since those can be
    modified via CLI now."""
    db.sql(
        """
        ALTER TABLE cf_run
        ADD COLUMN global_config JSON;

        INSERT INTO cf_meta (schema_version) VALUES (20260914);
    """
    )


def migration_20260918(db):
    """There seems to be weird typecasting happening sometimes for certain stages
    when adding the hash_debug information, as though it's trying to use a strict
    struct datatype instead of JSON. The hash_details are really only used for
    manual debugging and there's no need to _store_ as JSON, so just switching it
    to a string."""
    db.sql(
        """
        ALTER TABLE cf_stage
        ALTER hash_details TYPE VARCHAR;

        INSERT INTO cf_meta (schema_version) VALUES (20260918);
    """
    )


MIGRATIONS = {
    1: original_tables,
    20260210: migration_20260210,
    20260829: migration_20260829,
    20260914: migration_20260914,
    20260918: migration_20260918,
}
