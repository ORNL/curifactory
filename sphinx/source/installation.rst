Installation
############

Curifactory can be installed from pip via:

.. code-block:: bash

    pip install curifactory

Or from conda-forge with:

.. code-block:: bash

    conda install -c conda-forge curifactory

Note that graphviz must be installed for certain reporting features to work.
In conda, you can do this with:

.. code-block:: bash

    conda install python-graphviz


Curifactory comes with a CLI ``curifactory`` runnable, which can bootstrap a
curifactory-enabled project directory for you.

.. code-block:: bash

    curifactory init

This command will step you through the process. You can run it either in a new
folder or in an existing project, and it will create any necessary paths for
curifactory to work. Descriptions of the various folders created in the
initialization process are in the
:ref:`configuration and directory structure` section.

.. important::
    It is strongly recommended to use curifactory from within a git repo to
    support experiment reproducibility and provenance (every run will record the
    current git commit hash.) The ``curifactory init`` command will prompt you
    to run ``git init`` if the ``.git`` folder is not detected. Any experiment
    runs executed outside of a git repo will carry an associated warning in the
    output log and report.


Tab completion
==============

Curifactory comes with tab-completion in bash and zsh via the ``argcomplete`` package.
(If you're using curifactory from inside a conda environment, you'll need to install it
in your system python.)

.. code-block:: bash

    pip install argcomplete

To enable the tab-completion, you can either use argcomplete's global hook
``activate-global-python-argcomplete``, which will enable tab complete on all
argcomplete-enabled python packages (e.g. pytest), or you can add

.. code-block:: bash

    eval "$(register-python-argcomplete experiment)"

to your shell's rc file (``~/.bashrc`` or ``~/.zshrc``). Curfiactory can add this line
for you automatically with:

.. code-block::

    curifactory completion [--bash|--zsh]  # use the flag corresponding to your shell


Once enabled, the ``experiment`` CLI that curifactory provides will have tab completion
for experiment names, parameter file names, and flags.

..
    TODO: gif of what using argcomplete looks like
