"""Class for managing an experiment's map/dag logic."""

from curifactory.record import MapArtifactRepresentation, Record


class DAG:
    def __init__(self):
        self.records: list[Record] = []
        self.artifacts: list[MapArtifactRepresentation] = []
        """This should essentially be an equivalent copy of ArtifactManager.artifacts.
        All of record's stage inputs and outputs should correctly index into this."""

        self.execution_chain: list[tuple[int, str]] = []

    def get_record_string(self, record_index: int) -> str:
        """Get a string representation for a record."""
        record = self.records[record_index]
        output = (
            f"==== {record.get_reference_name(True)} hash: {record.get_hash()} ===="
        )
        for index, stage in enumerate(record.stages):
            output += "\nStage: " + stage
            if self.is_leaf(record, stage):
                output += " (leaf)"
            if len(record.stage_inputs[index]) > 0:
                output += "\n\tInputs:"
                for stage_input_index in record.stage_inputs[index]:
                    if stage_input_index != -1:
                        stage_input = self.artifacts[stage_input_index]
                        output += f"\n\t\t{stage_input.name}"
                        if stage_input.cached:
                            output += " (cached)"
            if len(record.stage_outputs[index]) > 0:
                output += "\n\tOutputs:"
                for stage_output_index in record.stage_outputs[index]:
                    stage_output = self.artifacts[stage_output_index]
                    output += f"\n\t\t{stage_output.name}"
                    if stage_output.cached:
                        output += f" (cached) [{stage_output.metadata['manager_run_info']['reference']}]"
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
        for output_index in outputs:
            output = self.artifacts[output_index]
            if self.is_output_used_anywhere(record, stage_index + 1, output.name):
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
            for stage_input_index in record.stage_inputs[i]:
                stage_input = self.artifacts[stage_input_index]
                if stage_input.name == output:
                    return True

        # check if any following records directly use in a stage or aggregate
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

    def find_leaves(self) -> list[tuple[int, str]]:
        """Returns a list of tuples where the first element is the record index and the
        second is the name of the stage."""
        leaves = []
        for index, record in enumerate(self.records):
            for stage in record.stages:
                if self.is_leaf(record, stage):
                    leaves.append((index, stage))

        return leaves

    def build_execution_chain_recursive(
        self, record: Record, stage: str, chain: list[tuple[int, str]]
    ) -> list[tuple[int, str]]:
        """Determines if the requested stage will need to execute or not, and if so prepends itself
        and all prior stages needed to execute by recursively calls."""
        stage_index = record.stages.index(stage)

        # first check if all of the outputs for this stage are cached, if any one of them is not,
        # will need to add to execution chain
        cached = True
        for stage_output_index in record.stage_outputs[stage_index]:
            stage_output: MapArtifactRepresentation = self.artifacts[stage_output_index]
            if not stage_output.cached:
                cached = False

        if cached:
            # no need to execute this stage, don't prepend to execution chain
            return chain

        # need to execute, prepend to chain
        chain.insert(0, (record.get_record_index(True), stage))

        # now recursively go through previous stages whose output is needed for this one and
        # continue to build execution chain.
        for stage_input_index in record.stage_inputs[stage_index]:
            stage_input: MapArtifactRepresentation = self.artifacts[stage_input_index]

            # TODO will need diff logic for aggregate?
            prereq_record = self.records[stage_input.record_index]
            prereq_stage = stage_input.stage_name
            chain = self.build_execution_chain_recursive(
                prereq_record, prereq_stage, chain
            )

        return chain

    def build_execution_chain(self):
        """Build up the full set of stages that need to run based on all of the leaves in
        the DAG."""
        self.execution_chain = []
        leaves = self.find_leaves()
        for leaf in leaves:
            leaf_record = self.records[leaf[0]]
            leaf_stage = leaf[1]
            self.execution_chain = self.build_execution_chain_recursive(
                leaf_record, leaf_stage, self.execution_chain
            )
