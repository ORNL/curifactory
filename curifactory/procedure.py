"""Convenience class for grouping stages and automatically passing a record between them."""

from typing import Callable

from curifactory.manager import ArtifactManager, Record
from curifactory.params import ExperimentParameters


class NoArtifactManagerError(Exception):
    pass


class Procedure:
    """A defined list of stages to run in sequence, creating a record to associate
    with them.

    For the stage list, specify only the names of the functions.

    Example:

        .. code-block:: python

            @stage(...)
            def data_stage(...):
                # ...

            @stage(...)
            def model_stage(...):
                # ...

            proc = Procedure(
                [
                    data_stage,
                    model_stage
                ],
                mngr)

    Args:
        stages list[Callable]: A list of function names that are wrapped in ``@stage`` or ``@aggregate``
            decorators. Note that if using an aggregate state, it _must_ be the first one in the
            list.
        manager (ArtifactManager): The manager to associate this procedure and corresponding record
            with. If this is ``None``, a manager will need to be passed when ``.run()`` is called.
        name (str): An optional name for the procedure. Currently unused, may eventually be put into
            logging or reporting.
        previous_proc (Procedure): If specified and this procedure begins with an aggregate stage,
            use the ``previous_proc.records`` list of records.
        records (List[Record]): If specified and this procedure begins with an aggregate stage, use
            this list of records. Note that ``previous_proc`` takes precedence over this argument.

    Note:
        If a procedure begins with an aggregate stage and neither ``previous_proc`` nor
        ``records`` are specified, it will automatically grab all existing records from the
        artifact manager.

    Note that you can predefine a procedure and "apply"/run it later, since the ``.run()`` function
    can take both a manager and records list directly.

    Example:

        .. code-block:: python

            @stage(...)
            def data_stage(...):
                # ...

            @stage(...)
            def model_stage(...):
                # ...

            proc = Procedure(
                [
                    data_stage,
                    model_stage
                ])

            def run(paramsets, manager):
                for paramset in paramsets:
                    proc.run(paramset, manager=manager)
    """

    def __init__(
        self,
        stages: list[Callable],
        manager: ArtifactManager = None,
        name: str = None,
        previous_proc: "Procedure" = None,
        records: list[Record] = None,
    ):
        # NOTE: pass in previous procedure to auto aggregate across just the records
        # from that previous procedure
        self.name = name
        self.stages = stages
        self.record = None
        self.manager = manager

        self.records = []  # keeps track of all records run through this procedure
        # this is just for convenience for being able to aggregate off previous proc
        self.previous_proc = previous_proc
        self.use_records = records

    def run(
        self,
        param_set: ExperimentParameters,
        record: Record = None,
        hide: bool = False,
        manager: ArtifactManager = None,
        records: list[Record] = None,
    ) -> Record:
        """Run this procedure with the passed parameter set. This allows easily running
        multiple parameter sets through the same set of stages and automatically getting a separate
        record for each.

        Args:
            param_set (ExperimentParameters): The parameteter set to put into the record created for
                this procedure.
            record (Record): If you have a specific record you want the procedure to use (e.g.
                if you're chaining multiple procedures and already have an applicable record to
                use from the previous one), pass it here. If unspecified, a new record will
                automatically be created for the passed args and relevant artifact manager.
            hide (bool): If ``True``, don't add the created record to the artifact manager.
            manager (ArtifactManager): If a manager hasn't been set yet on this procedure,
                do so now. An exception will be thrown if the manager has already been set on
                this procedure.
            records (list[Record]): If this procedure begins with an aggregate and the
                list of input records wasn't set on init, do so now.

        Returns:
            The returned output from the last stage in ``self.stages``.
        """
        # NOTE: don't try to add a check for if we're setting an already set
        # artifact manager - silently use whatever is already there. The reason
        # for this is if someone is calling .run on a procedure inside of a loop
        # and passing the manager there (for convenience we allow this)

        # handle setting any previously unset values that are passed directly
        if self.manager is None and manager is None:
            # We have to have a manager and we definitely shouldn't try to
            # create one on the fly!
            raise NoArtifactManagerError(
                "This procedure does not have an artifact manager. Either initialize it with one, or call with `proc.run(manager=...)`"
            )
        elif self.manager is None and manager is not None:
            self.manager = manager

        if records is not None:
            self.use_records = records

        # create a new record as needed
        if record is None:
            self.record = Record(self.manager, param_set, hide=hide)
            self.records.append(self.record)
        else:
            self.record = record

        for index, stage in enumerate(self.stages):
            if index == 0 and self.previous_proc is not None:
                # the first stage of a proc based on previous proc needs to be
                # an aggregate proc
                # if you don't explicitly pass previous proc, it will take all
                # records from manager
                output = stage(self.record, self.previous_proc.records)
            elif index == 0 and self.use_records is not None:
                output = stage(self.record, self.use_records)
            else:
                # Note that if the previous two conditions _weren't_ applicable but
                # the first stage is still an aggregate, the aggregate decorator correctly
                # handles converting the ``None`` that will be passed in for the records,
                # to the full list of records on the manager.
                output = stage(self.record)  # have to pass record into each stage

        return output
