"""Classes for managing an experiment's map/DAG logic."""

# NOTE: the "tree" concept is a little confusing linguistically in this file
# because the graph is being looked at both forwards and backwards. A "leaf
# stage" is a stage at the _end_ of the experiment graph, where its outputs are
# not needed as inputs in any other stages. However, for the DAG and treating
# the stage as a node, the leaf stages are actually "root nodes" for the
# execution trees, because we model all of a node's/stage's dependencies as its
# children/its subtree.

# It's also important to note that obviously trees are subsets of possible
# graphs, the DAG is not literally represented as the full actual graph, but a
# collection of the aforementioned execution trees. This is because for the
# purposes of the DAG we only care about this recursive backwards dependency
# pass. This means there's very possibly duplication across trees, in the case
# of nodes with outputs that are used in multiple other stages, but size isn't
# really going to be an issue, and (I think) it's much simpler to
# programatically construct and analyze it this way.


from curifactory.record import MapArtifactRepresentation, Record


class ExecutionNode:
    """Represents a particular stage for a particular record - a node in the
    overall experiment graph.

    Args:
        record (Record): The record in which this stage would execute.
        stage_name (str): The name of the stage that would execute.
    """

    def __init__(self, record: Record, stage_name: str):
        self.record = record
        self.stage_name = stage_name
        self.parent: ExecutionNode = None
        """The parent is a node that depends on this one/uses its outputs.
        (This means that the same execution node might appear in multiple
        execution trees, if its output is used by more than one other stage)"""

        self.dependencies: list[ExecutionNode] = []
        """Dependencies are the 'subtree' - the other nodes/stages that create
        the outputs that match this node's inputs."""

    def chain_rep(self) -> tuple[int, str]:
        """Return this node represented as a tuple of the record index and stage name."""
        return (self.record.get_record_index(True), self.stage_name)

    def __str__(self):
        return self.string_rep()

    def string_rep(self, level=0) -> str:
        """Recursively collect and return this node's index and name and that of
        its subtrees."""
        string = "\n"
        string += "  " * level
        string += f"({self.record.get_record_index(True)}, {self.stage_name})"
        for child in self.dependencies:
            string += child.string_rep(level + 1)
        return string


class DAG:
    """A DAG represents an entire mapped version of an experiment as a graph, where
    the nodes are stages and the connections are the outputs of one stage mapped to
    the associated inputs of another.

    The DAG is constructed as the first step of an experiment run (provided it isn't
    run with ``no_dag=True`` or ``--no-dag`` on the CLI), by setting the artifact
    manager to a special ``map_mode``. The experiment code is all run but every stage
    short circuits before execution and after collecting information about it
    (the record it's part of, what outputs are cached, etc.) This information is then
    used to determine which stages actually need to execute, working backwards from
    the leaf stages. This differs from curifactory's base ``no_dag`` mode because the
    need-to-execute for every stage is based primarily on whether any future stage
    actually requires this one's outputs and has a need-to-execute (resulting in a
    recursive check backwards from the leaf stages.)
    """

    def __init__(self):
        self.records: list[Record] = []
        self.artifacts: list[MapArtifactRepresentation] = []
        """This should essentially be an equivalent copy of ArtifactManager.artifacts.
        All of record's stage inputs and outputs should correctly index into this."""

        self.execution_list: list[tuple[int, str]] = []
        """This is the list of ExecutionNode individual (non-recursive) string
        representations: ``(RECORD_ID, STAGE_NAME)``"""

        self.execution_trees: list[ExecutionNode] = []
        """The set of node execution trees - each node here is a "leaf stage", or
        stage with no outputs that other stages depend on. This is essentially the
        inverted tree, because stage "leafs" will each be a root of an execution
        tree, where the sub-trees are all the dependencies required for it to run."""

    def analyze(self):
        """Construct execution trees and execution list."""
        self.build_execution_trees()
        self.determine_execution_list()

    def get_record_string(self, record_index: int) -> str:
        """Get a string representation for the given record. This collects
        all of the associated stages, inputs and outputs for each, and cache
        status for each artifact."""
        record = self.records[record_index]
        output = (
            f"==== {record.get_reference_name(True)} hash: {record.get_hash()} ===="
        )
        for index, stage in enumerate(record.stages):
            output += "\nStage: " + stage
            if self.is_leaf(record, stage):
                output += " (leaf)"
            if len(record.input_records) > 0:
                output += "\n\tInput records:"
                for input_record in record.input_records:
                    output += f"\n\t\t{input_record.get_reference_name(True)}"
            if len(record.stage_inputs[index]) > 0:
                output += "\n\tInputs:"
                for stage_input_index in record.stage_inputs[index]:
                    if stage_input_index != -1:
                        stage_input = self.artifacts[stage_input_index]
                        output += f"\n\t\t{stage_input.name}"
                        if stage_input.cached:
                            output += f" (cached) [{stage_input.metadata['manager_run_info']['reference']}]"
            if len(record.stage_outputs[index]) > 0:
                output += "\n\tOutputs:"
                for stage_output_index in record.stage_outputs[index]:
                    stage_output = self.artifacts[stage_output_index]
                    output += f"\n\t\t{stage_output.name}"
                    if stage_output.cached:
                        output += f" (cached) [{stage_output.metadata['manager_run_info']['reference']}]"
        return output

    def print_experiment_map(self):
        """Print the representations for each record."""
        string = ""
        for index, record in enumerate(self.records):
            string += self.get_record_string(index) + "\n"
        print(string)

    def is_leaf(self, record: Record, stage_name: str) -> bool:
        """Check if the given stage is a leaf, based on two conditions:

        1. Stage is a leaf if it has no output artifacts.
        2. Stage is a leaf if it has outputs but they aren't used as inputs in
            any other stages.
        """
        stage_index = record.stages.index(stage_name)
        outputs = record.stage_outputs[stage_index]

        # it's a leaf if no outputs
        if len(outputs) == 0:
            return True

        # it's a leaf if outputs are not used anywhere
        for output_index in outputs:
            output = self.artifacts[output_index]
            if self.is_output_used_anywhere(record, stage_index + 1, output.name):
                return False
        return True

    def is_output_used_anywhere(
        self, record: Record, stage_search_start_index: int, output: str
    ) -> bool:
        """Check if the specified output is used as input in any stage."""
        # Iterate each following stage in that record and see if the requested output
        # is in any of the inputs
        # TODO: instead of checking by name, we should be checking by the artifact id
        for i in range(stage_search_start_index, len(record.stages)):
            # NOTE: this works for both stages _and_ aggregates because expected_state
            # reps for aggregates get added to record.stage_inputs in the aggregate decorator
            for stage_input_index in record.stage_inputs[i]:
                stage_input = self.artifacts[stage_input_index]
                if stage_input.name == output:
                    return True

        # check if any following records directly use the output in a stage or aggregate
        children = self.child_records(record)
        for child in children:
            # check if we're directly using it in a normal stage
            explicitly_used = self.is_output_used_anywhere(child, 0, output)
            if explicitly_used:
                return True

        return False

    def child_records(self, record: Record) -> list[Record]:
        """Return a list of all records for which the provided record is an input record.
        (This occurs when calling ``record.make_copy()`` and for aggregates.)"""
        children = [
            other_record
            for other_record in self.records
            if record in other_record.input_records
        ]
        return children

    def find_leaves(self) -> list[tuple[int, str]]:
        """Get all of the nodes who have no outputs depended on by any others, these
        should be all of the "last" stages in the experiment and/or utility stages
        (e.g. a stage that just handles reporting or something like that/doesn't really
        output any artifacts.)

        Returns:
            a list of tuples where the first element is the record index and the
            second is the name of the stage.
        """
        leaves = []
        for index, record in enumerate(self.records):
            for stage in record.stages:
                if self.is_leaf(record, stage):
                    leaves.append((index, stage))

        return leaves

    def build_execution_tree_recursive(
        self, record: Record, stage: str
    ) -> ExecutionNode:
        """Recursively builds the stage dependency tree based on inputs/outputs. This does
        not condition anything based on cache or overwrite status, this is exclusively the
        "inverted" stage path (provided stage is the root)."""
        this_node = ExecutionNode(record, stage)

        # go through each input and get the record and stage that provides it as an output.
        # These are the dependencies, so recursively create nodes for them
        stage_index = record.stages.index(stage)
        for literal_input_index, stage_input_index in enumerate(
            record.stage_inputs[stage_index]
        ):
            # NOTE: literal_input_index is just the for loop index so we can index
            # into the associated string input names list on the record

            # Did we not find the input?
            if stage_input_index == -1:
                # if the stage's suppress missing inputs is set, just continue
                if record.stage_suppress_missing[stage_index]:
                    continue

                # if kwargs passed this input name, just continue
                if (
                    record.stage_inputs_names[stage_index][literal_input_index]
                    in record.stage_kwargs_keys[stage_index]
                ):
                    continue

                # otherwise throw a KeyError (see 260 staging.py)
                raise KeyError(
                    "Stage '%s' input '%s' not found in record state and not passed to function call. Set 'suppress_missing_inputs=True' on the stage and give a default value in the function signature if this should run anyway."
                    % (
                        stage,
                        record.stage_inputs_names[stage_index][literal_input_index],
                    )
                )

            stage_input: MapArtifactRepresentation = self.artifacts[stage_input_index]

            prereq_record = self.records[stage_input.record_index]
            prereq_stage = stage_input.stage_name

            sub_node = self.build_execution_tree_recursive(prereq_record, prereq_stage)
            sub_node.parent = this_node
            this_node.dependencies.append(sub_node)

        return this_node

    def build_execution_trees(self):
        """Build an execution tree (essentially the sub-DAG) for every leaf node found."""
        self.execution_trees = []
        leaves = self.find_leaves()
        for leaf in leaves:
            leaf_record = self.records[leaf[0]]
            leaf_stage = leaf[1]
            tree = self.build_execution_tree_recursive(leaf_record, leaf_stage)
            self.execution_trees.append(tree)

    def determine_execution_list(self):
        """I've got them on the list, they'll none of them be missed."""
        self.execution_list = []
        for node in self.execution_trees:
            self.determine_execution_list_recursive(node, False)

    def determine_execution_list_recursive(
        self, node: ExecutionNode, overwrite_check_only: False
    ) -> bool:
        """Determines if the requested stage will need to execute or not, and if so prepends
        itself and all prior stages needed to execute through recursive calls."""
        stage_index = node.record.stages.index(node.stage_name)

        # first check if all of the outputs for this stage are cached, if any one of them is not,
        # will need to add to execution chain
        cached = True
        for stage_output_index in node.record.stage_outputs[stage_index]:
            stage_output: MapArtifactRepresentation = self.artifacts[stage_output_index]
            if not stage_output.cached:
                cached = False
                break

        # there is a special case here where a stage has _no_ outputs. Since the
        # above loop is assuming cached by default, and we have no non-cached things
        # to prove otherwise, we will hit this point in the code with cached=True
        # we want stages with no outputs to always execute, so we check for that and
        # force cached False
        if len(node.record.stage_outputs[stage_index]) == 0:
            cached = False

        # -- overwrite seek mode --
        # (in this mode we add the node if and only if there's a sub node that's being overwritten.)

        overwrite_stage_found = False
        """set to true if either this stage is set to overwrite, or if something in the subtree is
        going to be overwritten"""

        if node.stage_name in node.record.manager.overwrite_stages:
            overwrite_stage_found = True

        # we don't bother stepping into this part if _this_ stage is specified to overwrite,
        # because in the dependencies required mode below we'll be going on to check dependency
        # stages normally anyway.
        if (
            cached and not node.record.manager.overwrite and not overwrite_stage_found
        ) or overwrite_check_only:
            # recursively go through previous stages whose output is needed for this one and
            # look for a stage on the manager's overwrite stages list.
            for sub_node in node.dependencies:
                overwrite_found = self.determine_execution_list_recursive(
                    sub_node, True
                )
                if overwrite_found:
                    overwrite_stage_found = True
                    break

            # if no dependencies need to be overwritten, we're good to stop going down.
            if not overwrite_stage_found:
                return False
            # otherwise continue into dependencies required mode (because we need to execute
            # this stage)

        # -- dependencies required mode --
        # (we hit this mode because we know this stage needs to execute, so now recursively go
        # through its dependencies to see if _those_ need to execute as well.)

        # need to execute, off with its head!
        if node.chain_rep() not in self.execution_list:
            self.execution_list.insert(0, node.chain_rep())
            # NOTE: for some weird reason in how I have this structured, if an overwrite stage
            # is found, the ordering of the execution list is in reverse of what it's supposed to be.
            # For right now that doesn't really matter, but if we ever get fancy with using the DAG
            # to directly run functions, it will be important to fix this.

        # now recursively go through previous stages whose output is needed for this one and
        # continue to build execution list.
        for sub_node in node.dependencies:
            self.determine_execution_list_recursive(sub_node, False)

        # the output from this is technically only checked for inside the overwrite seek mode
        # I think
        return overwrite_stage_found
