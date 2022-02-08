Parameter files and argsets
===========================

Another goal of Curifactory is to allow effective parameterization of experiments. Where this might normally be
done with a json or yaml file, Curifactory directly uses python files for experiment parameterization/configuration.
This has a few advantages:

1. Arguments can be any python object, rather than simply a primitive type or dictionary.
2. Parameter files can reference/use other parameter files, allowing modularity and composition.
3. The resulting arguments that are passed into an experiment can be algorithmically generated or modified inside an
   arguments script file, with the full power of the python language! An example for how this might be useful is a single
   arguments script that generates 10 very similar argument sets for comparison, rather than having to individually define
   10 different parameter configuration files. This could allow custom gridsearches for example.

.. note::

    Throughout this documentation, we refer to "paramset" and "argset" as slightly different. A **"paramset"** refers
    to a whole parameters script file, while an **"argset"** refers to a single :code:`Args` instance. A single paramset
    returns one or more argsets in a list.

The :code:`Args` class
----------------------

As discussed on the :ref:`Getting Started` page, To define possible arguments, there should be a
class that inherits :code:`curifactory.ExperimentArgs`, and for ease of use should have the
:code:`@dataclass` decorator. By default, the cookiecutter project places an :code:`Args` class
for this inside of the :code:`params/__init__.py`. Possible arguments are the variables within
this class, and by defining default values for each one, this allows an arguments file to define
only what it needs to change from the defaults.

An example :code:`Args` class is shown below:

.. code-block:: python

    from dataclasses import dataclass, field
    from typing import List

    from curifactory import ExperimentArgs


    @dataclass
    class Args(ExperimentArgs):
        example_arg: str = ""
        example_number_of_epochs: int = 10

        # due to how dataclasses handle initialization, default lists and dictionaries need to
        # be handled with field factory from the dataclasses package.
        example_data: List[int] = field(default_factory=lambda: [1,2,3,4])


The actual parameter files (by default go in the :code:`params/` folder) are then each expected to define a
:code:`get_params()` function, which should return a list of :code:`Args` instances. A very simple example based on
the above :code:`Args` class might look like:

.. code-block:: python

    from params import Args

    def get_params():
        return [Args(name='test_params', example_number_of_epochs=15)]

.. note::

    As :code:`Args` is a completely user-defined class, you can technically name this class whatever you
    choose. The rest of this documentation is written under the assumption it is named "Args".

Programmatic definition
-----------------------

The :code:`get_params()` function can contain arbitrary code, and this is where advantages 2 and 3 listed above can be
exploited. For instance, if we wanted to define a set of parameters for testing multiple different numbers of epochs,
we could return a list of multiple :code:`Args`, each with a different epochs number:

.. code-block:: python

    from params import Args

    def get_params():
        args = []
        for i in range(5, 15):
            args.append(Args(name=f"epochs_run_{i}", example_number_of_epochs=i))
        return args

If we wanted to make parameter sets compositional, we can import one of the other parameter files and
reference its :code:`get_params()` call in the new one:

.. code-block:: python

    from params import base, Args

    def get_params():
        args = base.get_params()
        args[0].name = 'modified' # assuming we know there's only one Args instance (otherwise we do this in a loop)
        args[0].starting_data = [0, 2, 4, 6]
        return args

In the above example, there's another parameters file named :code:`base`, we get its arguments with :code:`base.get_params()`,
run our modifications, and return the modified argsets. In this way, any changes that get made to the base parameters also influence
this one, allowing for a form of parameter set hierarchy.

We can also create common functions for helping build up large amounts of argsets. As an example, we may frequently
wish to create "seeded" argsets, where we have the same arguments several times but with a different seed for sklearn
models or similar. Rather than manually define this, or reimplementing it in every relevant :code:`get_params()` function,
we could extract it as in this example:

.. code-block:: python
    :caption: params/common.py

    from copy import deepcopy
    from params import Args

    def seed_set(args: Args, seed_count: int = 5):
        seed_args = []
        for i in range(seed_count):
            # Make a copy of the passed args and apply a different seed
            new_args = deepcopy(args)
            new_args.name += f"_seed{i}"
            new_args.seed = i
            seed_args.append(new_args)
        return seed_args


.. code-block:: python
    :caption: params/seeded_models.py

    from params import Args
    from params.common import seed_set

    def get_params():
        knn_args = Args(name="test_knn", model_type="knn")
        svm_args = Args(name="test_svm", model_type="svm")

        all_args = []
        all_args.extend(seed_set(knn_args))
        all_args.extend(seed_set(svm_args, 3))

        return all_args



Using args
----------

Every stage automatically has access to the currently relevant :code:`Args` instance, as it is part of
the passed record.

.. code-block:: python

    from curifactory import Record

    import params
    import src

    @stage(['training_data'], ['model'])
    def train_model(record: Record, training_data):
        args: params.Args = record.args # use the type hinting to get good autocomplete in IDEs

        if args.model_type == "knn":
            # pass relevant args into the codebase functions
            src.train_knn(args.seed)
            # ...
