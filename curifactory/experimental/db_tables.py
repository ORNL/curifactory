"""Functions to manage/create/update curifactory store database tables."""

import duckdb

import curifactory.experimental as cf

SCHEMA_VERSION = 20260210

SCHEMAS = {
    "cf_run": [
        "id UUID",
        "reference VARCHAR",
        "pipeline_class VARCHAR",
        "pipeline_name VARCHAR",
        "run_number INTEGER",
        "start_time TIMESTAMP",
        "end_time TIMESTAMP",
        "succeeded BOOL",
        "exception VARCHAR",
        "exception_stack VARCHAR",
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


def ensure_tables(db):
    for table, cols in SCHEMAS.items():
        cols_str = ",\n".join(cols)
        db.sql(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                {cols_str}
            );
        """
        )
    if get_schema_version(db) == 0:
        db.sql(f"INSERT INTO cf_meta (schema_version) VALUES ({SCHEMA_VERSION})")


def verify_schemas(db):
    broken = False
    errors = {}
    for table, cols in SCHEMAS.items():
        existing_cols = (
            db.sql(f"SELECT column_name FROM (DESCRIBE {table})")
            .df()
            .column_name.values
        )
        for col in cols:
            col_name = col[: col.index(" ")]
            if col_name not in existing_cols:
                if table not in errors:
                    errors[table] = []
                errors[table].append((col_name, "missing"))
                broken = True
    return broken, errors


def intervention_add_missing_columns(db):
    broken, errors = verify_schemas(db)
    for table in errors:
        for error in errors[table]:
            if error[1] == "missing":
                col_name = error[0]
                # find the column in schema
                for col in SCHEMAS[table]:
                    if col[: col.index(" ")] == col_name:
                        print(f"\tAdding missing column {col}")
                        db.sql(f"ALTER TABLE {table} ADD COLUMN {col}")


def get_schema_version(db) -> int:
    try:
        schema_version = db.sql("SELECT MAX(schema_version) FROM cf_meta").fetchone()[0]
    except duckdb.CatalogException:
        schema_version = 1
    if schema_version is None:
        schema_version = 0
    return schema_version


def run_migrations(db):
    from curifactory.experimental import db_migrations

    starting_version = get_schema_version(db)
    for migration_version, migration in db_migrations.MIGRATIONS.items():
        if migration_version > starting_version:
            cf.get_manager().logger.info(f"Running migration {migration_version}...")
            migration(db)


FIXES = {"add_missing_columns": intervention_add_missing_columns}
