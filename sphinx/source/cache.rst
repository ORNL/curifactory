Cache
=====

Including a list of cachers in your stage decorators helps store intermediate results
both for easier exploration as well as faster re-execution.

There are four pre-implemented cachers that come with Curifactory in the :ref:`Caching`
module that should cover most basic needs:

* :code:`JsonCacher`
* :code:`PandasCsvCacher`
* :code:`PandasJsonCacher` - stores a dataframe as a json file (array of dictionaries, the keys as column names.)
* :code:`PickleCacher`

As a last resort, most things should be cacheable through
the :code:`PickleCacher`, but the advantage of using the :code:`JsonCacher` where
applicable allows you to manually browse through
the cache easier, instead of needing to write a script to load a piece
of cached data before viewing it.

Some things may not cache correctly even with a :code:`PickleCacher`,
such as pytorch models or similarly complex objects. For these, you
can write your own "cacheable" and plug it into a decorator in the same
way as the pre-made cachers.

Implementing a custom cacheable requires extending the :class:`caching.Cacheable <curifactory.caching.Cacheable>`
class, and the new class must have a :code:`load()` and :code:`save()`
function. The base class has a :code:`path` attribute that both functions can assume
is set correctly to a base path where it is appropriate to write any necessary files.
Following is an example:

.. code-block:: python

    import pickle
    from curifactory.caching import Cacheable

    class TorchModelCacher(Cacheable):
        def __init__(self):
            super().__init__("") # you would normally pass a string extension here if desired

        def save(self, obj):
            torch.save(obj.model.state_dict(), self.path + "_model")
            with open(self.path, 'wb') as outfile:
                pickle.dump(obj, outfile)

        def load(self):
            with open(self.path, 'rb') as infile:
                obj = pickle.load(infile)
            obj.model.load_state_dict(torch.load(self.path + "_model", map_location="cpu"))
            return obj


In this example, we've defined a custom cacher for some python class that contains a torch model inside of it, in
the :code:`.model` attribute.
Using pickle for the torch model itself is discouraged, but we still want to store the whole class as well.
The custom cacher therefore saves to two separate files - first we save the model state dict with a :code:`_model`
suffix, then pickle the whole class. On load we reverse this process, by unpickling the whole class and then
replacing the model attribute with the more appropriate :code:`load_state_dict` results.

You can then pass this class name in a cachers list in the stage decorator as if it were one of the premade
cacheables:

.. code-block:: python

    @stage(inputs=..., outputs=["trained_model"], cachers=[TorchModelCacher])
    def train_model(record, ...):
        # ...


Lazy cache objects
------------------

While caching by itself helps reduce overall computation time when re-running
experiments over and over, if running sizable experiments with a lot of large data
in state at once, memory can be a problem. Many times, when stages are
appropriately caching everything, some objects don't need to be in
memory at all because they're never used in a stage that actually runs. To
address this, curifactory has a :code:`Lazy` class. This class is used by
wrapping it around the string name in the outputs array:

.. code-block:: python

    @stage(inputs=..., outputs=["small_object", Lazy("large-object")], cachers=...)

When an output is specified as lazy, as soon as the stage computes, the output
object is cached and removed from memory. The :code:`Lazy` instance is then inserted
into the state. Whenever the :code:`large-object` key is accessed on the state,
it uses the cacher to reload the object back into memory (but maintains the Lazy
object in state, so as long as no references persist beyond the stage, it will
stay out of memory.

Because lazy objects rely on a cacher, cachers should always be specified for
these stages. If no cachers are given, curifactory will automatically use a
:code:`PickleCacher`.

When a stage with a Lazy object is computed the second time, the cachers check
for their appropriate files as normal, and if they are found the lazy output
again keeps only a :code:`Lazy` instance in the record state rather than
reloading the actual file.
