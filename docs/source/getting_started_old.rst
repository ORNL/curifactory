Getting started
===============

Installation
------------

Installing via the `cookiecutter project <https://github.com/ORNL/cookiecutter-curifactory>`_ is strongly recommended:

.. code-block:: bash

    git clone https://github.com/ORNL/cookiecutter-curifactory.git
    pip install curifactory
    cookiecutter ./cookiecutter-curifactory

(Follow the cookiecutter prompts.)

The cookiecutter can be applied to an existing code repo with the :code:`-f` flag and
providing the existing folder name when prompted for the project name:

.. code-block:: bash

    cookiecutter ./cookiecutter-curifactory -f
    project_name [project_name]: [EXISTING_FOLDER_NAME]

If you'd prefer to manually create a project without using cookiecutter, you can set up
a minimal directory structure with:

.. code-block:: bash

    mkdir -p data/cache data/runs logs reports notebooks/experiments experiments params stages
    pip install curifactory

Descriptions of the various folders can be found in the :ref:`configuration and directory structure`
section.

It is also recommended to install graphviz for better output reports. If using
conda, this can be done with :code:`conda install python-graphviz`


Components in brief
-------------------

This section very briefly covers the components involved in Curifactory. More in
depth descriptions and diagrams of the innerworkings can be found in the
in-depth :ref:`components` section.

Curifactory consists of three primary components: experiment files, parameter
files, and stages.

* A **stage** is a specially decorated function that represents some step in an
  experimental process, such as loading/cleaning data. A stage handles
  routing/making calls into the actual codebase and appropriately passing necessary
  arguments from **parameter files**.
* **Parameter files** are python scripts that programatically define lists of
  configuration :code:`ExperimentArgs` classes and set all necessary parameters
  to configure a piece of an experiment run. (Defining these as python scripts
  as opposed to static JSON configuration files allows lots of fancy things, for more
  information see the :ref:`Parameter files and argsets` section.)
* **Experiment files** are python scripts that create and run lists of **stages**,
  and are in charge of routing passed parameter sets (which come from the
  **parameter files**) into the stages.

.. figure:: curifactory_overview_simpler.png
    :align: center

    Experiments route parameters into lists of stages, stages route relevant
    parameters into codebase calls.


Example project
---------------

Below we step through a very simple working example project. This example project
turns a simple "research codebase" that trains a few sklearn
algorithms into a runnable/parameterizable experiment. We'll step through
creating stages to wrap around the codebase, parameter files to configure runs,
and finally write the experiment script to tie the stages together.
By the end, the final directory structure should look like:

.. code-block::

    experiments/
        example.py
    params/
        __init__.py
        simple_lr.py
        multiple_rf.py
    stages/
        example_stages.py
    src/
        models.py


Research code
.............

Our underlying research codebase for the example will simply be a couple of
functions for creating, training, and testing an sklearn classifier (either a
logistic regression algorithm or random forest) on sample data.

.. code-block:: python
    :caption: src/models.py

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    def train_logistic_regression(X, y, balanced=False, seed=42):
        class_weight = 'balanced' if balanced else None
        clf = LogisticRegression(class_weight=class_weight, random_state=seed)
        clf.fit(X, y)
        return clf

    def train_random_forest(X, y, n=100, balanced=False, seed=42):
        class_weight = 'balanced' if balanced else None
        clf = RandomForestClassifier(n, class_weight=class_weight random_state=seed)
        clf.fit(X, y)
        return clf

    def test_model(X_test, y_test, clf):
        score = clf.score(X_test, y_test)
        y_pred = clf.predict(X_test)

        return score, y_pred


Stages
......

Next we create stages to represent the various parts of the experiment we want
to run, which in this case might simply be :code:`load_data`, :code:`train_model`, and
:code:`test_models`.

A stage is defined by wrapping a :code:`@stage` decorator around a function. The
decorator takes two, (optionally three) parameters: inputs, outputs, and
cachers. Curifactory keeps track of an "experiment state", which is just a
dictionary of variable names and their associated values from throughout the
run. This state is made available to every stage and automatically populates function
calls - :code:`inputs` specify the list of string variable names it wants from the state,
and the :code:`outputs` write the function return values to the specified variables in
the state. The final and optional parameter is :code:`cachers`, where you provide
a list of cacher classes, each associated with an output variable. (Curifactory
comes with a set of default cachers, see the :ref:`Cache` section.)

.. code-block:: python
    :caption: stages/example_stages.py

    from typing import List

    from curifactory import stage, aggregate, Record
    from curifactory.caching import PickleCacher
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    from params import Args
    from src import models

    @stage(inputs=[], outputs=['df', 'x_train', 'y_train', 'x_test', 'y_test'], cachers=[PickleCacher]*5)
    def load_data(record: Record):
        args: Args = record.args

        data = load_iris()

        x = data.data
        y = data.target
        df = data.frame

        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=args.test_percent, random_state=args.seed)

        return df, x_train, y_train, x_test, y_test

Breaking down this snippet, we start with the decorator and function:

.. code-block:: python

    @stage(inputs=[], outputs=['df', 'x_train', 'y_train', 'x_test', 'y_test'], cachers=[PickleCacher]*5)
    def load_data(record: Record):

Every stage is expected to take a :code:`Record` instance as the first argument.
This is what the experiment manager uses to maintain state and automatically transfer data
between different stages. Since there are no inputs listed, no other input
params in the function header line are required. The 5 outputs indicate that
this function should return 5 things, and will all afterwards appear in the
:code:`record.state` dictionary under the specified keys. The
:code:`PickleCacher` which we import from :code:`curifactory.caching` is the
type of cacher we want to use for all five outputs, meaning running this stage
will create a pickle file in the cache directory for each output variable. When
rerunning the stage, if it finds those pickle files, it will load and return
them using the PickleCacher load function, without needing to execute the stage
code.

The remainder of the stages are shown below:

.. code-block:: python
    :caption: stages/example_stages.py (continued)

    @stage(inputs=['x_train', 'y_train'], outputs=['model'], cachers=[PickleCacher])
    def train_model(record: Record, x_train, y_train):
        args: Args = record.args

        if args.model_type == "lr":
            clf = model.train_logistic_regression(x_train, y_train, args.balanced, args.seed)
        elif args.model_type == "rforest":
            clf = model.train_random_forest(x_train, y_train, args.n, args.balanced, args.seed)

        return clf

    @aggregate(outputs=["scores"], cachers=None)
    def test_models(record: Record, records: List[Record]):
        scores = {}

        for prev_record in records:
            if "model" in prev_record.state:
                score, y_pred = models.test_model(
                    prev_record.state["x_test"],
                    prev_record.state["y_test"],
                    prev_record.state["model"]
                )
                scores[prev_record.args.name] = score

        return scores

Note that in :code:`train_model`, the names of the parameters :code:`x_train` and :code:`y_train`
must exactly match the names in the stage inputs list :code:`inputs=['x_train, 'y_train']`, as this
is how these parameters are automatically populated internally.

The :code:`test_models` stage uses an :code:`@aggregate` decorator instead of
a stage decorator:

.. code-block:: python

    @aggregate(outputs=["scores"], cachers=None)
    def test_models(record: Record, records: List[Record]):

Where a normal stage is intended to run a piece of an experiment for a single parameter set,
aggregate stages are intended to work across passed parameter sets. They do not
take any explicit inputs, instead taking a list of previous records (by default
all of them) to operate on. Aggregate stage functions are expected to take their
own record as the first argument, and the list of records to use as the second.

.. figure:: aggregates.png
   :align: center

To operate on the previous records and run comparisons across them, we iterate
the passed records list and collect data from them through their :code:`state`
variable.

.. code-block:: python

    for prev_record in records:
        # if a record has a model in it, test it
        if "model" in prev_record.state:
            score, y_pred = models.test_model(
                # use the testing data contained within that records' state
                prev_record.state["x_test"],
                prev_record.state["y_test"],
                prev_record.state["model"]
            )


Parameters
..........

Parameter files allow us to easily make different configurations to experiment with. These configurations should
live in :code:`Args` classes, which extend Curifactory's :code:`ExperimentArgs` class. It is recommmended to define
your :code:`Args` class in a :code:`params/__init__.py` file. To make it
syntactically nicer to work with, use a python :code:`@dataclass`:

.. code-block:: python
    :caption: params/__init__.py

    from dataclasses import dataclass

    from curifactory import ExperimentArgs

    @dataclass
    class Args(ExperimentArgs):
        balanced: bool = False
        """Whether class weights should be balanced or not."""
        n: int = 100
        """The number of trees for a random forest."""
        seed: int = 42
        """The random state seed for data splitting and model training."""
        model_type: str = "lr"
        """Which sklearn model to use, 'lr' or 'rforest'."""

We then create the parameter files. All valid parameter files are expected to
have a :code:`get_params()` function, which should return a list of your
:code:`Args` instances. This means that a single parameter file can create
multiple argument sets. When you run an experiment and specify multiple
parameter files, all lists of arguments are turned into one single list and
passed into the experiment.

A simple example defining a single :code:`Args` is shown below, for running a
logistic regression algorithm with balanced data:

.. code-block:: python
    :caption: params/simple_lr.py

    from typing import List

    from params import Args

    def get_params() -> List[Args]:
        return [Args(
            name='simple_lr',
            balanced=True,
            model_type="lr",
            seed=1
        )]

Note that since :code:`Args` extends Curifactory's :code:`ExperimentArgs`, it
has a few additional variables by default, most importantly :code:`name`, which
should be different for every :code:`Args` instance to make it easier to report
on and debug.

We can programatically define a parameter file to return multiple :code:`Args`
instances each with a different size random forest with this example:

.. code-block:: python
    :caption: params/multiple_rf.py

    from typing import List

    from params import Args

    def get_params() -> List[Args]:
        sizes = [10, 20, 30]
        args = []

        for size in sizes:
            args.append(Args(
                name=f"multi_rf_{size}",
                n=size,
                model_type="rforest"
            ))
        return args


The experiment
..............

The final implementation detail is to create an experiment to stitch the stages
together and orchestrate how arguments get passed into them.

A simple working experiment script for our example project follows:

.. code-block:: python
    :caption: experiments/example.py

    from typing import List

    from curifactory import ArtifactManager, Procedure

    from params import Args
    from stages.example_stages import load_data, train_model, test_models

    def run(argsets: List[Args], mngr: ArtifactManager):
        # define basic procedure
        proc = Procedure([load_data, train_model], mngr)

        # run all parameters through procedure
        for args in argsets:
            proc.run(args)

        # run aggregate stage
        Procedure([test_models], mngr).run(None)

All valid experiment files are expected to define a :code:`run(argsets,
manager)` function, which takes a list of :code:`Args` to test and an instance
of Curifactory's :code:`ArtifactManager`, which holds and manages many of the
overarching details of an experiment run.

While stages can be run manually, for convenience we use a :code:`Procedure`
which lets us list the stages to run in order, and calling
:code:`run(ARGS_INSTANCE)` on the resulting object runs the stage set with the
passed :code:`Args`:

.. code-block:: python

        proc = Procedure([load_data, train_model], mngr)

        # ...

        proc.run(args)

As aggregate stages run across records and may not have a clearly defined
associated :code:`Args`, you can pass :code:`None` as the args to procedures
that begin with an aggregate stage.

.. code-block:: python

    Procedure([test_models], mngr).run(None)


Running the experiment
......................

Curifactory ships with an :code:`experiment` commandline tool for easily running
experiments. To get a listing of all runnable experiments and parameter files,
run:

.. code-block:: bash

   experiment ls

To run the experiment we just created with both parameter files, run:

.. code-block:: bash

   experiment example -p simple_rl -p multiple_rf

Note that we reference experiment and parameter files by name but do not include
the .py extension.


Next steps
----------

Look through:

* :ref:`Components` for a more in-depth understanding of the components and how they
  interact with each other.
* :ref:`Parameter files and argsets` for fancier things you can do with parameters.
* :ref:`Cache` for how to make custom cachers.
* :ref:`Reports` to get an idea for how reports work and how to use them, plus how
  to make custom reportables.
* :ref:`CLI guide` for how to use the :code:`experiment` CLI program and what you can
  do with it.
* :ref:`Tips and tricks` for various "patterns" of use for Curifactory.
