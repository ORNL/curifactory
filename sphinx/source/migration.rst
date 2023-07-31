Migration Guide
###############

Any breaking API changes that will need to be accounted for/will likely require
updates to your experiment code will be documented here with explanations of
how to do so.


0.14.0 - 0.15.0
===============

The naming scheme for "args"/parameters has been cleaned up and "args" is no longer a
concept in curifactory. The ``args`` module has been renamed to ``params``, and the
base parameter class ``ExperimentArgs`` has been renamed to ``ExperimentParameters``.

The following changes will need to be made in any previous experiments:

Change any ``Record.args`` references to ``Record.params``
----------------------------------------------------------

This will likely effect every stage that uses parameters, e.g.

.. code-block:: python

    @stage(...)
    def train_model(record: cf.Record):
        model = LogisticRegression(random_state=record.args.seed_args)

Should now become:

.. code-block:: python

    @stage(...)
    def train_model(record: cf.Record):
        model = LogisticRegression(random_state=record.params.seed_args)


Classes subclassing ``curifactory.args.ExperimentArgs`` should subclass ``curifactory.params.ExperimentParameters``
-------------------------------------------------------------------------------------------------------------------

The ``args`` module has been renamed to ``params``, so any imports that explicitly
reference ``curifactory.args`` will need to be changed to ``curifactory.params``.
Similarly, the base parameter class that you extend for custom parameters will
need to be changed from ``ExperimentArgs`` to ``ExperimentParameters``:

.. code-block:: python

    from curifactory import ExperimentParameters

    @dataclass
    class MyParams(ExperimentParameters):
        ...

Both of the above changes are currently optional, ``Record.args`` and
``curifactory.args.ExperimentArgs`` exist with deprecation warnings. These will likely be
fully removed in version 0.16.0.


0.13.0 - 0.14.0
===============

Aggregate stages should now specify ``inputs`` in the decorator
---------------------------------------------------------------

Along with the addition of DAG-based stage execution, ``@aggregate`` stages now
have an ``inputs`` attribute in the decorator, which similarly to the ``@stage``
decorator should include the string names of all artifacts in all aggregated
records that will be needed in the aggregate stage code.

Specifying ``inputs`` is required for the DAG to map the experiment correctly,
not doing so will likely cause any stages before the aggregate (that it would
otherwise rely on) to never execute.

Similar to ``@stage``, any listed input strings need a corresponding argument
of the same name in the function definition. Each of these arguments will be
populated with a dictionary where each key is a record, and the value is the
corresponding artifact of that name from that record's state. This allows
simplifying aggregate stage code, as you no longer need to directly access
the state from each record.

An example to demonstrate required/suggested changes follows, assume that
this stage is trying to take all of the results from previous records and
put them into a single dictionary, where the keys are the names of the parameter
sets that generated the associated result metric:

A previous aggregate stage would have been:

.. code-block:: python

    @aggregate(outputs=["final_results"])
    def combine_results(record: Record, records: list[Record]):
        final_results = {}
        for r in records:
            if "results" in r.state:
                final_results[r.args.name] = r.state["results"]
        return final_results


This code could now be changed to:

.. code-block:: python

    @aggregate(inputs=["results"], outputs=["final_results"])
    def combine_results(record: Record, records: list[Record], results: dict[Record, float]):
        final_results = {}
        for r, result in results.items():
            final_results[r.args.name] = result
        return final_results

Note that the *minimum amount of changes to still function* would simply involve
adding the ``inputs`` and the corresponding function definition argument, the inner
stage code itself doesn't need to change.

.. code-block:: python

    @aggregate(inputs=["results"], outputs=["final_results"])
    def combine_results(record: Record, records: list[Record], results: dict[Record, float]):
        final_results = {}
        for r in records:
            if "results" in r.state:
                final_results[r.args.name] = r.state["results"]
        return final_results


Any specified ``inputs`` that don't appear in one or more of the passed records'
states will print a warning **but will not error.** The associated argument's
dictionary will simply not contain that record.


.. note::

    To temporarily retain previous ``v0.13.x`` behavior for aggregate stages that you
    do not yet specify ``inputs`` for, you can run the experiment with the ``--no-dag``
    CLI flag.
