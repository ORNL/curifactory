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
    db.sql(
        """
        ALTER TABLE cf_run
        ADD COLUMN exception VARCHAR;

        ALTER TABLE cf_run
        ADD COLUMN exception_stack VARCHAR;

        INSERT INTO cf_meta (schema_version) VALUES (20260210);
    """
    )


MIGRATIONS = {
    1: original_tables,
    20260210: migration_20260210,
}
