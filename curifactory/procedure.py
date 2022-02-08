"""Convenience class for grouping stages and automatically passing a record between them."""

from curifactory.manager import Record, ArtifactManager


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
        stages: A list of function names that are wrapped in :code:`stage` or :code:`aggregate`
            decorators. Note that if using an aggregate state, it _must_ be the first one in the
            list.
        manager (ArtifactManager): The manager to associate this procedure and corresponding record
            with. If you specify :code:`None`, one will be created with the default constructor.
        name (str): An optional name for the procedure. Currently unused, may eventually be put into
            logging or reporting.
        previous_proc (Procedure): If specified and this procedure begins with an aggregate stage,
            use the :code:`previous_proc.records` list of records.
        records (List[Record]): If specified and this procedure begins with an aggregate stage, use
            this list of records.

    Note:
        If a procedure begins with an aggregate stage and neither :code:`previous_proc` nor
        :code:`records` are specified, it will automatically grab all existing records from the
        artifact manager.
    """

    def __init__(
        self, stages, manager=None, name=None, previous_proc=None, records=None
    ):
        # TODO: allow manager to be none as well to just create a local manager (e.g. if you wanted to run
        # a procedure within a notebook)
        # NOTE: pass in previous procedure to auto aggregate across just the records
        # from that previous procedure
        self.name = name
        self.stages = stages
        self.record = None
        self.manager = manager
        if manager is None:
            self.manager = (
                ArtifactManager()
            )  # TODO: notably this doesn't respect the config.

        self.records = []  # keeps track of all records run through this procedure
        # this is just for convenience for being able to aggregate off previous proc
        self.previous_proc = previous_proc
        self.use_records = records

    def run(self, args, record=None, hide=False):
        """Run this procedure with the passed set of args. This allows easily running
        multiple argsets through the same set of stages and automatically getting a separate
        record for each.

        Args:
            args (ExperimentArgs): The args to put into the record created for this procedure.
            record (Record): If you have a specific record you want the procedure to use (e.g.
                if you're chaining multiple procedures and already have an applicable record to
                use from the previous one), pass it here. If unspecified, a new record will
                automatically be created for the passed args and relevant artifact manager.
            hide (bool): If :code:`True`, don't add the created record to the artifact manager.

        Returns:
            The returned output from the last stage in :code:`self.stages`.
        """
        # create a new record as needed
        if record is None:
            self.record = Record(self.manager, args, hide=hide)
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
                output = stage(self.record)  # have to pass record into each stage

        return output
