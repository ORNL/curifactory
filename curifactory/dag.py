"""Class for managing an experiment's map/dag logic."""

from curifactory.record import Record


class DAG:
    def __init__(self):
        self.records: list[Record] = []

    def get_record_string(self, record_index: int) -> str:
        """Get a string representation for a record."""
        record = self.records[record_index]
        output = (
            f"==== {record.get_reference_name(True)} hash: {record.get_hash()} ===="
        )
        for index, stage in enumerate(record.stages):
            output += "\nStage: " + stage
            if len(record.stage_inputs[index]) > 0:
                output += "\n\tInputs:"
                for stage_input in record.stage_inputs[index]:
                    if stage_input != -1:
                        output += f"\n\t\t{stage_input.name}"
                        if stage_input.cached:
                            output += " (cached)"
            if len(record.stage_outputs[index]) > 0:
                output += "\n\tOutputs:"
                for stage_output in record.stage_outputs[index]:
                    output += f"\n\t\t{stage_output.name}"
                    if stage_output.cached:
                        output += " (cached)"
            if len(record.input_records) > 0:
                output += "\n\tInput records:"
                for input_record in record.input_records:
                    output += f"\n\t\t{input_record.get_reference_name(True)}"
        return output

    def print_experiment_map(self):
        """Print representations for each record."""
        string = ""
        for index, record in enumerate(self.records):
            string += self.get_record_string(index) + "\n"
        print(string)

    def is_leaf(self, record: Record, stage_name: str) -> bool:
        stage_index = record.stages.index(stage_name)
        outputs = record.stage_outputs[stage_index]

        # it's a leaf if no outputs
        if len(outputs) == 0:
            return True

        # it's a leaf if outputs are not used anywhere
        found_used = False
        for output in outputs:
            if not self.is_output_used_anywhere(record, stage_index + 1, output.name):
                found_used = True
        if not found_used:
            return True

        return False

    def is_output_used_anywhere(
        self, record: Record, stage_search_start_index: int, output: str
    ) -> bool:
        """Check if the specified output is used as input in any stage"""
        # Iterate each following stage in that record and see if the requested output
        # is in any of the inputs
        for i in range(stage_search_start_index, len(record.stages)):
            # TODO: doesn't work because inputs are reps not strings
            if output in record.stage_inputs[i]:
                return True

        # check if any following records directly use in a stage or if
        children = self.child_records(record)
        for child in children:
            # check if we're direclty using it in a normal stage
            explicitly_used = self.is_output_used_anywhere(child, 0, output)
            if explicitly_used:
                return True

            # check if there's an aggregate in which we _might_ be using it.
            if child.is_aggregate:
                # TODO: will eventually want to use the "expects_state" here
                return True

        return False

    # TODO: don't like this name
    def child_records(self, record: Record) -> list[Record]:
        """Return a list of all records for which the provided record is an input record."""
        children = [
            other_record
            for other_record in self.records
            if record in other_record.input_records
        ]
        return children
