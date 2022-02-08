Tips and tricks
===============

Minimum code to run stages
--------------------------

Directly/manually running stages can be useful for a variety of reasons, whether for debugging them,
using the same configuration values as from an experiment, or as a basis for exploration in
a jupyter notebook.

The smallest set of components needed to do this is an :code:`Args` instance, an
:code:`ArtifactManager`, and a :code:`Record`:

.. code-block:: python

    # required components
    from curifactory import ArtifactManager, Record
    from params import Args

    # import whatever stages you need to run
    from stages.data import get_data, clean_data

    # initialize instances of the required components
    args = Args() # create/initialize the args. Note that you could also directly load
                  # and manually call the get_params() of a paramset script
    mngr = ArtifactManager("some_cache_ref_name") # the caching prefix name (normally
                                                  # the experiment name)
    record = Record(mngr, args)

    # run desired stages
    clean_data(get_data(record))

    # get the return from the last run stage (you could also get it from record.state)
    print(record.output)

Note that calling any stage, e.g. :code:`get_data(record)` returns the modified record that
was passed in, and since calling a stage always only takes exactly one parameter, (the record
to use) you can directly chain the stages together with :code:`clean_data(get_data(record))`


Common dataset for multiple different argsets
---------------------------------------------

For some experiments, you may have a single dataset processing procedure that all other argsets should
share. By default, caching only applies to a single argset, so the data would have to be recomputed for
every argset, if you defined your entire experiment in one procedure. However, it's possible to write
your experiment to "share" the state of a data processing record with the remainder of your argsets.

.. code-block:: python

    def run(argsets: List[Args], mngr: ArtifactManager):

        # define the procedures
        common_data_proc = Procedure([get_data, clean_data], mngr) # the resulting state of this procedure
                                                                   # should be the same for all our
                                                                   # argsets, so we only want to run it
                                                                   # once
        model_proc = Procedure([train_model, test_model], mngr) # this procedure is where we expect our
                                                                # argsets to differ, so run it per argset

        # run our common procedure once (assuming all of the relevant args are _actually_ the same, we can
        # just pull from the first one)
        data_record = common_data_proc.run(argsets[0])

        # run each argset through model procedure
        for argset in argsets:
            record = data_record.make_copy(argset) # duplicate the data record's state but with new args
            model_proc.run(argset, record) # we can manually specify the record to use in a procedure if
                                           # we already have one

The above will result in an experiment graph that looks something like the following, assuming two argsets:

.. figure:: images/common_proc.png
    :align: center

The :code:`make_copy()` function on :code:`Record` instances creates a new record with a deepcopy of the
:code:`state` attribute, meaning you can define procedures that only have later stages, and pass them
the copied records.

This can be extended beyond just common datasets - any baseline procedure that will not change state
across different argsets in a given experiment can follow this same pattern.


Branching in experiments
------------------------

When running experiments that compare many different approaches, it is likely you'll need to
run different procedures for different argsets (as different stages may be necessary, for example in
training an sklearn algorithm versus a model implemented in pytorch.) Since experiment scripts are
arbitrary, you can create arguments intended solely for use in the experiment itself, and simply branch
based on those arguments for each given argset:

.. code-block:: python

    def run(argsets: List[Args], mngr: ArtifactManager):
        proc1 = Procedure([get_data, clean_data, train_sklearn_alg, test_model], mngr)
        proc2 = Procedure([get_data, clean_data, train_pytorch, test_model], mngr)

        for argset in argsets:
            # we assume "model_type" is one of the arguments
            if argset.model_type == "sklearn":
                proc1.run(argset)
            elif argset.model_type == "pytorch":
                proc2.run(argset)

        Procedure([compile_results], mngr).run(None) # an appropriately constructed
                                                     # aggregate stage can still run
                                                     # to compare outputs across multiple
                                                     # procedures.


Using the git commit hash from reports
--------------------------------------

Every time an experiment is run, the experiment store keeps track of the current git commit hash.
If you need to be able to exactly reproduce an experiment, ensure that all code is committed before
the run, and run it with the :code:`--full-store` flag (see the :ref:`Full stores` section.)
The output report from your run will contain the git commit hash in the top metadata fields, as well
as the command to reproduce it with the correct cache.

To re-run, checkout that hash in git, and enter the reproduce command given in the report:

.. code-block:: bash

    git commit
    experiment some_experiment -p some_params --store-full

    # review the report to get the appropriate run reproduce command and the git commit hash

    # to exactly reproduce:
    git checkout [COMMIT_HASH]
    experiment some_experiment -p some_params --cache data/runs/[RUN_REF_NAME] --dry-cache
