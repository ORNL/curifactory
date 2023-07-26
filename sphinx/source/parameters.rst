Parameter files and parameter sets
==================================

Another goal of Curifactory is to allow effective parameterization of experiments. Where this might normally be
done with a json or yaml file, Curifactory directly uses python files for experiment parameterization/configuration.
This has a few advantages:

1. Parameters can be any python object, rather than simply a primitive type or dictionary.
2. Parameter files can reference/use other parameter files, allowing modularity and composition.
3. The resulting parameter sets that are passed into an experiment can be algorithmically generated or modified inside an
   parameter file, with the full power of the python language! An example for how this might be useful is a single
   parameter file that generates 10 very similar parameter sets for comparison, rather than having to individually define
   10 different parameter configuration files. This could allow custom gridsearches for example.

.. note::

    Throughout this documentation we use specific language to refer to different parts of parameterization:

    * **Parameter** - a single parameter is a single attribute of a parameter class.
    * **Parameter class** - a dataclass that extends curifactory's ``ExperimentParameters`` and defines the possible hyperparameters.
    * **Parameter set** - an instance of a parameter class, every stage operates on a record with a single specific parameter set.
    * **Parameter file** - a python script as defined below that creates one or more parameter sets.

The :code:`ExperimentParameters` class
--------------------------------------

As discussed on the :ref:`Getting Started` page, To define possible parameters, there should be a
class that inherits :code:`curifactory.ExperimentParameters`, and for ease of use should have the
:code:`@dataclass` decorator. Possible parameters your experiment stages can use are the attributes
within this class, and by defining default values for each one, a parameter set constructor need only
specify the parameters that differ from the defaults.

An example :code:`Params` class is shown below:

.. code-block:: python

    from dataclasses import dataclass, field

    from curifactory import ExperimentParameters


    @dataclass
    class Params(ExperimentParameters):
        example_param: str = ""
        example_number_of_epochs: int = 10

        # due to how dataclasses handle initialization, default lists and dictionaries need to
        # be handled with field factory from the dataclasses package.
        example_data: list[int] = field(default_factory=lambda: [1,2,3,4])


The actual parameter files (by default go in the ``params/`` folder) are then each expected to define a
``get_params()`` function, which should return a list of ``Params`` instances. A very simple example based on
the above ``Params`` class might look like:

.. code-block:: python

    from params import Params

    def get_params():
        return [Params(name='test_params', example_number_of_epochs=15)]

.. note::

    As ``Params`` is a completely user-defined class, you can technically name this class whatever you
    choose. The rest of this documentation is written under the assumption it is named ``Params``.


.. warning::

   While the parameters in your dataclass can be arbitrary types, weird issues
   can sometimes arise if you include non-serializable objects. We've run into
   problems with things like including a pytorch distributed strategy object as
   an argument, as it can end up in a weird recursive serialization loop when
   curifactory tries to get a serialized JSON string representation of the
   corresponding arguments.



Programmatic definition
-----------------------

The ``get_params()`` function can contain arbitrary code, and this is where advantages 2 and 3 listed above can be
exploited. For instance, if we wanted to define sets for testing multiple different numbers of epochs,
we could return a list of multiple ``Params`` instances, each with a different epochs number:

.. code-block:: python

    from params import Params

    def get_params():
        param_sets = []
        for i in range(5, 15):
            param_sets.append(Params(name=f"epochs_run_{i}", example_number_of_epochs=i))
        return param_sets

If we wanted to make parameter sets compositional, we can import one of the other parameter files and
reference its ``get_params()`` call in the new one:

.. code-block:: python

    from params import base, Params

    def get_params():
        param_sets = base.get_params()
        param_sets[0].name = 'modified' # assuming we know there's only one Args instance (otherwise we do this in a loop)
        param_sets[0].starting_data = [0, 2, 4, 6]
        return param_sets

In the above example, there's another parameters file named ``base``, we get its arguments with ``base.get_params()``,
run our modifications, and return the modified argsets. In this way, any changes that get made to the base parameters also influence
this one, allowing for a form of parameter set hierarchy.

We can also create common functions for helping build up large amounts of argsets. As an example, we may frequently
wish to create "seeded" argsets, where we have the same arguments several times but with a different seed for sklearn
models or similar. Rather than manually define this, or reimplementing it in every relevant ``get_params()`` function,
we could extract it as in this example:

.. code-block:: python
    :caption: params/common.py

    from copy import deepcopy
    from params import Params

    def seed_set(params: Params, seed_count: int = 5):
        seed_params = []
        for i in range(seed_count):
            # Make a copy of the passed params and apply a different seed
            new_params = deepcopy(params)
            new_params.name += f"_seed{i}"
            new_params.seed = i
            seed_params.append(new_params)
        return seed_params


.. code-block:: python
    :caption: params/seeded_models.py

    from params import Params
    from params.common import seed_set

    def get_params():
        knn_params = Params(name="test_knn", model_type="knn")
        svm_params = Params(name="test_svm", model_type="svm")

        all_params = []
        all_params.extend(seed_set(knn_params))
        all_params.extend(seed_set(svm_params, 3))

        return all_params

Calling the ``get_params()`` in the ``params/seeded_models.py`` parameter file would return:

.. code-block:: python

    [
        Params(name='test_knn_seed0', model_type='knn', seed=0)
        Params(name='test_knn_seed1', model_type='knn', seed=1)
        Params(name='test_knn_seed2', model_type='knn', seed=2)
        Params(name='test_knn_seed3', model_type='knn', seed=3)
        Params(name='test_knn_seed4', model_type='knn', seed=4)
        Params(name='test_svm_seed0', model_type='svm', seed=0)
        Params(name='test_svm_seed1', model_type='svm', seed=1)
        Params(name='test_svm_seed2', model_type='svm', seed=2)
    ]


Using parameters
----------------

Every stage automatically has access to the currently relevant ``Params`` instance, as it is part of
the passed record.

.. code-block:: python

    from curifactory import Record

    from params import Params
    import src

    @stage(['training_data'], ['model'])
    def train_model(record: Record, training_data):
        params: Params = record.params # use the type hinting to get good autocomplete in IDEs

        if params.model_type == "knn":
            # pass relevant parameters into the codebase functions
            src.train_knn(params.seed)
            # ...

Parameter set hashes and operational parameters
-----------------------------------------------

Curifactory automatically versions cached artifacts based on the parameter set used. It does this
by computing a hash (the full details of which can be found on the :ref:`Hashing` page,) which
involves taking a form of string representation of the value for every attribute in a parameter
set and computing the combined md5 hash.

There are a few types of cases where we may want to modify how that hash is being computed

1. Some parameters may be "operational", they influence how an experiment runs but shouldn't change the results.
2. By default the ``repr`` of some times of objects may not correctly return a value that uniquely and consistently represents what we want it to.

Say we have the following dataclasses:

.. code-block:: python

    @dataclass
    class Params(cf.ExperimentParameters):
        model_size: int = 9000
        num_gpus: int = 1

If we create two parameter sets with different gpu counts, we get two different hashes:

.. code-block:: python

    p1 = Params(name="one_gpu", num_gpus=1)
    p2 = Params(name="two_gpus", num_gpus=2)

    p1.params_hash()
    #> '1ae3169d21cc23f1665561f7e91fe266e'
    p2.params_hash()
    #> 'f1b00c12e820963221b1f60501d3822e'

This would mean any stages we run these two parameter sets through would compute and cache two
sets of outputs. However, we may want to change the number of gpus we use (when moving between
machines), and we want it to use the same cached values because we wouldn't expect the results
to change.

Curifactory will look for a special ``hash_representations`` dictionary on any ``ExperimentParameters``
class or composed dataclass on an ``ExperimentParameters`` subclass instance, which can optionally
contain string keys of one or more of the attributes on the parameter class and an associated function
that is passed the entire parameter set instance as well as the value of that specific parameter. By
setting that function to ``None``, we can tell Curifactory to ignore that parameter as part of the hash.

Since setting default dictionaries on dataclasses requires an annoying amount of syntax, Curifactory
provides a ``set_hash_functions`` function to initialize it correctly.

If we want to ignore ``num_gpus``, it might look like this:

.. code-block:: python

    @dataclass
    class Params(cf.ExperimentParameters):
        model_size: int = 9000
        num_gpus: int = 1

        hash_representations: dict = cf.set_hash_functions(num_gpus=None)

If we now run the same code as above:

.. code-block:: python

    p1 = Params(name="one_gpu", num_gpus=1)
    p2 = Params(name="two_gpus", num_gpus=2)

    p1.params_hash()
    #> 'b50ba553739feea66c8aab97787c22e0'
    p2.params_hash()
    #> 'b50ba553739feea66c8aab97787c22e0'


If we specify an actual function, that function takes both the whole parameter set
as well as the specified parameter, meaning we can condition the hash representation
for a specific parameter based on the others. (This is primarily useful if a parameter
is a complex object and the ``repr`` doesn't include some of the parameters it was
initialized with.)

As a simplistic and somewhat silly example, we can condition our model_size hash
representation on num_gpus:

.. code-block:: python

    @dataclass
    class Params(cf.ExperimentParameters):
        model_size: int = 9000
        num_gpus: int = 1

        hash_representations: dict = cf.set_hash_functions(
            num_gpus=None,
            model_size=lambda self, obj: str(obj/self.num_gpus)
        )

.. code-block:: python

    p1 = Params(name="one_gpu", model_size=4500, num_gpus=1)
    p2 = Params(name="two_gpus", model_size=9000, num_gpus=2)
    p3 = Params(name="big_one_gpu", model_size=9000, num_gpus=1)

    p1.params_hash()
    #> 'a04bd13c314c694d8f1cff76cc34d2b'
    p2.params_hash()
    #> 'a04bd13c314c694d8f1cff76cc34d2b'
    p3.params_hash()
    #> 'ff1275fb121412c666259c7baefbf4e9'
