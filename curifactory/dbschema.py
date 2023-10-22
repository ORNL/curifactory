"""The metadata and table definitions for sqlalchemy for the experiment store."""

# TODO: will need to decide beteen Core and ORM usage
# from sqlalchemy import MetaData, Table, Column


# metadata_obj = MetaData()
#
# store_info = Table(
#
# )
#

# https://docs.sqlalchemy.org/en/20/tutorial/metadata.html

from sqlalchemy.orm import (
    DeclarativeBase,
    ForeignKey,
    Mapped,
    mapped_column,
    relationship,
)

# TODO: it may be useful to have a module that just tracks per-version schemas,
# and this file loads in the correct version based on dbinfo?


class Base(DeclarativeBase):
    pass


class DBInfo(Base):
    """We probably expect to have a "version", "user", and "machine" properties."""

    __tablename__ = "db_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str]
    value: Mapped[str]


class Run(Base):
    __tablename__ = "run"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )  # TODO id should maybe actually be ref name
    reference: Mapped[str]
    experiment_name: Mapped[str]
    run_number: Mapped[int]
    timestamp: Mapped[str]  # TODO: maybe we can make this an actual datetime stamp now?
    commit: Mapped[str]
    param_files: Mapped[list["RunParamFileNames"]] = relationship(back_populates="run")

    # params

    full_store: Mapped[bool]
    status: Mapped[str]
    cli: Mapped[str]
    hostname: Mapped[str]
    user: Mapped[str]
    notes: Mapped[str]


class RunParamFileNames(Base):
    __tablename__ = "run_param_file_name"

    id: Mapped[int] = mapped_column(primary_key=True)

    run_id = mapped_column(ForeignKey("run.id"))
    run: Mapped[Run] = relationship(back_populates="param_files")


# TODO: need a run param_file_name to paramname and param hash
