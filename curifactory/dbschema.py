"""The metadata and table definitions for sqlalchemy for the experiment store."""

# TODO: will need to decide beteen Core and ORM usage
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table

metadata_obj = MetaData()

store_info = Table(
    "store_info",
    metadata_obj,
    Column("key", String, primary_key=True),
    Column("value", String),
)

runs_table = Table(
    "run",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("reference", String),
    Column("experiment_name", String),
    Column("run_number", Integer),
    Column("timestamp", DateTime),
    Column("commit", String),
    Column("param_files", String),  # NOTE: this will be a json.dumps,
    # since this is likely to change in later cf versions, I don't want
    # to bother correctly normalizing this part of the table, since I
    # don't think there will be need to query on it anyway.
    Column("params", String),
    Column("workdir_dirty", Boolean),
    Column("full_store", Boolean),
    Column("status", String),
    Column("cli", String),
    Column("hostname", String),
    Column("user", String),
    Column("notes", String),
)


# https://docs.sqlalchemy.org/en/20/tutorial/metadata.html
# https://docs.sqlalchemy.org/en/20/tutorial/data_insert.html#tutorial-core-insert
