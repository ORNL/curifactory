Experiment Graph (DAG)
######################


An experiment in curifactory can be thought of as a graph, where the stages are nodes in the graph, and
any artifact produced as an output and one stage and consumed as an input in another connects those
two nodes with an edge. (This is somewhat explicitly represented in the stage graphs included in experiment
reports.)

When curifactory executes an experiment, it runs two "phases", technically running the ``run`` function twice.
The first time is in "map mode" (where the ``ArtifactManager``'s ``map_mode`` is set to ``True``.) During this
map mode, no stage content is actually executed, curifactory simply steps into each stage decorator to collect
information about the artifacts, associated recors and parameter sets, and what outputs are cached.

Curifactory then uses this information to help determine what stages actually need to execute. This is done
technically by a set of sort of "reverse execution trees" rather than a true DAG - it determines which
stages are "leaf nodes" (stages that aren't depended on by any other stages), and then works backwards
through its dependencies (and which dependencies are cached or requested overwrites) to create a list of
stages in specified records that will need to be run to produce the leaf node outputs.


There are two benefits to note that arise from this functionality:

1. If you specify ``--overwrite-stage`` for some early on stage in the experiment, the DAG will automatically
   apply to every later stage that directly or indirectly (through a dependency chain) depended on that stage's
   outputs and will mark those for execution as well.
2. If you have an experiment you're iterating on or sharing with others, as long as the final stage outputs
   are passed along too and in their cache, re-executing the experiment won't try to re-execute all the intermediate
   stages (with missing cache artifacts) because only the final ones are needed.
