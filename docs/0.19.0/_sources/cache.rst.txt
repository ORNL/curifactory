Cache
=====

Curifactory makes it straightforward to store and re-use intermediate artifacts generated
throughout an experiment with its caching mechanisms. During an experiment run, user-specified
caching strategies dump parameter-set-versioned instances of stage outputs in a common cache folder,
and when running a stage that already has the appropriate artifacts in the cache for the current
parameter set, it uses the caching strategy to reload the artifact from cache instead of executing
the stages. Storing artifacts in cache both helps re-execute the experiment faster as well as
creates a "paper trail" for manual exploration of the artifacts.

Caching strategies are ``Cacher`` classes that extend curifactory's base ``Cacheable`` class. Using
these cachers is as easy as listing them in your stage decorator for each output the stage generates:

.. code-block:: python

    from curifactory import stage
    from curifactory.caching import PandasJsonCacher, JsonCacher, PickleCacher

    @stage(outputs=["dataset", "metrics_dictionary", "model"], cachers=[PandasJsonCacher, JsonCacher, PickleCacher])
    def return_all_the_things(record):
        ...
        return dataset, metrics, model


There are several pre-implemented cachers that come with Curifactory in the :ref:`Caching`
module that should cover many basic needs:

* ``JsonCacher``
* ``PandasCacher`` - store a dataframe using a specified format
* ``PandasCsvCacher``  - shortcut for ``PandasCacher(format='csv')``
* ``PandasJsonCacher`` - shortcut for ``PandasCacher(format='json')``, stores a dataframe as a json file (array of dictionaries, the keys as column names.)
* ``PickleCacher``
* ``FileReferenceCacher`` - a json file that stores references to one or more file paths.
* ``RawJupyterNotebookCacher`` - turns a list of list of strings of python code into a jupyter notebook

As a last resort, most things should be cacheable through
the ``PickleCacher``, but the advantage of using the ``JsonCacher`` where
applicable allows you to manually browse through
the cache easier, instead of needing to write a script to load a piece
of cached data before viewing it.

Some things may not cache correctly even with a ``PickleCacher``,
such as pytorch models or similarly complex objects. For these, you
can write your own "cacheable" and plug it into a decorator in the same
way as the pre-made cachers.

Implementing a custom cacheable requires extending the :class:`caching.Cacheable <curifactory.caching.Cacheable>`
class, and the new class must have a ``save(obj)`` and ``load() -> obj``
function, which respectively should handle saving the passed artifact to disk,
and loading and returning a reconstructed artifact.

The base ``Cacheable`` has a ``get_path()`` function which the cacher implementation can assume
correctly returns a full filepath including the correct versioned filename for the current artifact.
In the case that a cacher needs to save more than one file or wants to provide a different suffix for
the filename, this can be passed to ``get_path``.

.. code-block:: python

    import pickle
    from curifactory.caching import Cacheable

    class TorchModelCacher(Cacheable):
        def __init__(self, *args, **kwargs):
            # NOTE: it is recommended to always include and pass *args and **kwargs
            # in custom cachers to allow functionality specified in the Cacher arguments section
            super().__init__(*args, extension=".model_obj" **kwargs)

        def save(self, obj):
            torch.save(obj.model.state_dict(), self.get_path("_model"))
            with open(self.get_path(), 'wb') as outfile:
                pickle.dump(obj, outfile)

        def load(self):
            with open(self.get_path(), 'rb') as infile:
                obj = pickle.load(infile)
            obj.model.load_state_dict(torch.load(self.get_path("_model"), map_location="cpu"))
            return obj

.. note::

    It is recommended to always include and pass ``*args`` and ``**kwargs`` in custom cachers to allow
    consistent functionality as specified in :ref:`Cacher arguments`.

.. warning::

    The returns from ``get_path()`` calls should be used exactly for the paths written to and read from -
    Curifactory internally tracks the ``get_path()`` outputs for determining what to copy to a full
    store folder, so if you write to ``get_path() + "something.json"``, it won't correctly track that path.
    Instead, use the suffix capability: ``get_path("something.json")``. If you have a lot of files to save,
    or need to do complicated path manipulation, instead use ``self.get_dir()`` as the base path, and
    curifactory will track the entire subfolder.


In this example, we've defined a custom cacher for some python class that contains a torch model inside of it, in
the ``.model`` attribute.
Using pickle for the torch model itself is discouraged, but we still want to store the whole class as well.
The custom cacher therefore saves to two separate files - first we save the model state dict with a ``_model``
suffix, then pickle the whole class. On load we reverse this process, by unpickling the whole class and then
replacing the model attribute with the more appropriate ``load_state_dict`` results.

You can then pass this class name in a cachers list in the stage decorator as if it were one of the premade
cacheables:

.. code-block:: python

    @stage(inputs=..., outputs=["trained_model"], cachers=[TorchModelCacher])
    def train_model(record, ...):
        # ...


Using cachers
-------------


Cacher arguments
................

As specified above, you can use a cacher in a stage simply by providing the class name in the cachers list.
You can also initialize the cacher in the list, and there are several parameters that provide additional control
over the path that's used by the cacher.

* **overwrite_path**: specifying this completely overrides all other path computation functionality and uses
  the provided path exactly. If using this in a stage decorator, that means it won't use any form of parameter
  set hash versioning.   This is useful in situations where a stage is effectively a static transform that
  isn't affected by any parameters.
* **subdir**: if specified, uses this subdirectory in front of the filename, both within the cache directory
  and within a full store run's artifacts directory.
* **prefix**: By default, the experiment name is used as the prefix for every cached filepath. If there are specific
  artifacts that are safe to use across all experiments that call the stage this cacher is used from, you can specify
  the prefix here.
* **track**: Tracked filepaths are paths that get copied into a full store run. This is always true by default, but
  there can be situations (especially when dealing with very large artifacts such as datasets) where it's not desirable
  to keep a copy of every single artifact. Setting this to ``False`` does **not** disable caching it normally into
  the cache directory, but it will not transfer that file to the full store run artifacts directory.

Inline cachers
..............

While the primary purpose of cachers is to use them as a "strategy" to specify to a stage, cachers can also be
used inline, either directly in a stage or in any normal code. This is useful in cases where you need to manually
load an artifact, and you have the path for it already.

.. code-block:: python

    some_metrics_path = ...
    metrics = JsonCacher(some_metrics_path).load()

You can also get the metadata associated with the artifact:

.. code-block:: python

    some_metrics_path = ...
    cacher = JsonCacher(some_metrics_path)
    metrics = cacher.load()
    metadata = cahcer.load_metadata()


Metadata
--------

Every cached artifact saves an associated metadata json file that tracks information about the cacher,
the current record, and the experiment run. This metadata file is copied along with the artifact in
full store runs, and is kept when an artifact is re-used in a later run.

This metadata dictionary is available on every cacher object through ``.metadata``. In addition, every
``Cacheable`` object has an ``.extra_metadata`` dictionary that custom cachers can use to store additional
information either for provenance/informational use, or to help direct loading code. This extra metadata
gets added to the cacher's ``metadata`` when saving, and is populated from a ``.load_metadata()`` call.

An example might look like:

.. code-block:: python

    class UsesExtraMetadataCacher(Cacheable):
        def save(self, obj):
            self.extra_metadata["the_best_number"] = 13
            JsonCacher(self.geet_path()).save(obj)

        def load(self):
            assert self.extra_metadata["best_number"] == 13
            return JsonCacher(self.get_path()).load()

The curifactory stage decorator automatically handles calling ``save_metadata()`` and ``load_metadata()`` at
the appropriate times for the above cacher to work. However, if you're using this custom cacher inline, these
functions are never explicitly called. If you want to enable this cacher to work inline, you need to add in
explicit save/load metadata calls in the save/load functions:


.. code-block:: python

    class UsesExtraMetadataCacher(Cacheable):
        def save(self, obj):
            self.extra_metadata["the_best_number"] = 13
            self.save_metadata()
            JsonCacher(self.get_path()).save(obj)

        def load(self):
            self.load_metadata()
            assert self.extra_metadata["best_number"] == 13
            return JsonCacher(self.get_path()).load()



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


Lazy resolve
............

By default, every time a ``Lazy`` instance is passed into a stage wrapped function, it resolves to
the object itself, meaning it calls the load function on the associated cacher. If a ``Lazy`` instance
is specified with ``resolve=False``, then every time that artifact is used as input, the input that gets
passed is the actual ``Lazy`` instance itself.

The primary value in this is to be able to access the associated cacher from within a stage in order to
get its path (this is useful when doing external calls.)
