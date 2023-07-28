Hashing Mechanics
#################

As discussed in :ref:`Parameter set hashes and operational parameters`, curifactory computes a hash of
every parameter set run through an experiment, and uses that hash to uniquely identify/version the outputs
associated with it. This page discusses in more detail how the hash is computed and how you can modify it.

The overall process involves iterating through every field of the parameter class, getting a string
representation for the value of each, computing the md5 hash of that string, summing up the
integer values of each md5 hash, and then turning this final (very large number) into a hexidecimal
string. We sum the individual md5 hashes so that the order in which the fields are iterated doesn't
affect the hash.

There is an ordered list of mechanisms that curifactory will go through to try produce
the string representation:

1. If it's an internal curifactory parameter, skip it, don't let it influence the hash.  This
   includes ``name``, ``hash``, ``overwrite``, and the ``hash_representations`` field itself.
2. If the value of the parameter is ``None``, skip it.
3. If the current field is in this parameter class's ``hash_representations``, call its specified
   function (or skip this parameter if the value is ``None``)
4. If the parameter is another dataclass, recursively use all of these mechanics on the fields inside
   it.
5. If the parameter is a callable, use its ``__qualname__``
6. Otherwise default to calling ``repr`` on it.


"Skipping" a parameter only means it does not take part in determining the hash. If you
run ``my_param_set.params_hash(dry=True)``, instead of returning the hash it will return
the computed dictionary of hashing mechanisms to be used on every attribute and the string
representation that will be passed to the md5 hashing algorithm. For any parameter that
will be skipped, it will list the reason why. See example below:

.. code-block:: python


    @dataclass
    class Params(ExperimentParameters):
        some_value: int = 5
        operational_param: int = 9
        something_crazy: any = "crazy"
        nothing: int = None

        hash_representations: dict = set_hash_functions(
            operational_param=None,
            something_crazy=lambda self, obj: str(obj)
        )


    Params(name="test", some_value=6).params_hash(dry=True)
    #> {'name': ('SKIPPED: blacklist', None),
    #>  'hash': ('SKIPPED: blacklist', None),
    #>  'overwrite': ('SKIPPED: blacklist', None),
    #>  'hash_representations': ('SKIPPED: blacklist', None),
    #>  'some_value': ('repr(param_set.some_value)', '6'),
    #>  'operational_param': ('SKIPPED: set to None in hash_representations', None),
    #>  'something_crazy': ("param_set.hash_representations['something_crazy'](param_set, param_set.something_crazy)",
    #>   'crazy'),
    #>  'nothing': ('SKIPPED: value is None', None)}


Skipping parameters in a single set
===================================

As demonstrated so far, we can set the ``hash_representations`` on the parameter class itself with
``set_hash_functions``, and this is normally the preferred way to ensure a particular parameter always
gets ignored for the hash. However, sometimes it makes sense to only ignore a parameter in a one or a couple
cases, perhaps for all the parameter sets coming from a single parameter file.

You can set the ``hash_representations`` on the fly after creating a parameter set:

.. code-block:: python

    @dataclass
    class Params(ExperimentParameters):
        i_matter: int = 5
        sometimes_i_matter: int = 7

    p1 = Params(name="test", i_matter=3)

    p2 = Params(name="test2", i_matter=2)
    p2.hash_representations["sometimes_i_matter"] = None

    p1.params_hash(dry=True)
    #> { ...
    #>  'i_matter': ('repr(param_set.i_matter)', '3'),
    #>  'sometimes_i_matter': ('repr(param_set.sometimes_i_matter)', '7')}

    p2.params_hash(dry=True)
    #> { ...
    #>  'i_matter': ('repr(param_set.i_matter)', '2'),
    #>  'sometimes_i_matter': ('SKIPPED: set to None in hash_representations', None)}


The outputs of the dry params hash calls above shows that p1 includes the actual value of the
``sometimes_i_matter`` parameter, while p2 skips it.
