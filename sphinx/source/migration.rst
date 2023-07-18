Migration Guide
###############

Any breaking API changes that will need to be accounted for/will likely require
updates to your experiment code will be documented here with an explanations of
how to do so.

0.14.0 - 0.15.0
===============

The naming scheme for "args"/parameters has been cleaned up and "args" is no longer a
concept in curifactory. The ``args`` module has been renamed to ``params``, and the
base parameter class ``ExperimentArgs`` has been renamed to ``ExperimentParameters``.

The following changes will need to be made in any previous experiments:
* ``Record.args`` -> ``Record.params``. This will likely effect every stage that uses
    parameters, e.g.

.. code-block:: python

    @stage(...)
    def train_model(record: cf.Record):
        model = LogisticRegression(random_state=record.args.seed_args)

Should now become:

.. code-block:: python

    @stage(...)
    def train_model(record: cf.Record):
        model = LogisticRegression(random_state=record.params.seed_args)

* ``curifactory.args.ExperimentArgs`` -> ``curifactory.params.ExperimentParameters``, the
    module has been renamed, so any imports that explicitly reference ``curifactory.args``
    will need to be changed to ``curifactory.params``. Similarly, the base parameter class
    that you extend from will need to be changed from ``ExperimentArgs`` to
    ``ExperimentParameters``:

.. code-block:: python

    from curifactory import ExperimentParameters

    @dataclass
    class MyParams(ExperimentParams):
        ...

Both of the above changes are currently optional, ``Record.args`` and
``curifactory.args.ExperimentArgs`` exist with deprecation warnings. These will likely be
fully removed in version 0.16.0.

0.13.0 - 0.14.0
===============

TODO (the expected state for aggregates)
