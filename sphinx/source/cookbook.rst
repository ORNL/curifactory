Curifactory Cookbook
####################

This page contains a set of recipes or solutions to challenges we've encountered.


Distributed ``torchrun`` via external stage
===========================================

Training pytorch models in distributed mode can sometimes cause issues in curifactory - when running
on GPUs with DDP, pytorch will start a new process for each GPU and run a copy of whatever command
initially spawned it. If directly setting up a pytorch lightning trainer inside a stage, this means
that each process will be re-running the entire curifactory experiment.

In theory this should be fine - curifactory can detect the MPI env variables and put itself into
``--parallel-mode``, and as long as stages are set up appropriately any work prior to the trainer
should already be cached anyway. However, in practice we've run into performance issues.

A pattern that works relatively well in curifactory to get around this is having a stage act simply
as a wrapper around an external command - using either ``os.system`` or ``subprocess.run`` (or even
curifactory's own internal utility for this, ``curifactory.utils.run_command``) to run a separate
python script (or any other CLI tool, this can be a way to integrate with other languages and
applications), and then passing in parameters as CLI args, artifact inputs as paths, and desired
output locations as paths.

The stage then handles getting the associated paths of everything, constructing the CLI line, running it,
and then loading any outputs back into curifactory and returning them.

In particular, we've found it pretty easy to use the click python library to quickly make an external
python function into something callable by a stage.


.. code-block:: python
    :caption: external/my_model_trainer.py

    import click
    from pytorch_lightning import Trainer
    from pytorch_lightning.callbacks import ModelCheckpoint


    @click.command()
    @click.option("--dataset_path", type=str)   # input artifact path
    @click.option("--model_path", type=str)     # output artifact path
    @click.option("--checkpoint_dir", type=str)
    @click.option("--num_gpus", type=int)       # a parameter
    def train_model(dataset_path, model_path, checkpoint_dir, num_gpus):
        # load data from dataset_path however needed
        ...

        checkpoint_callback = ModelCheckpoint(
            dirpath=checkpoint_dir, verbose=True, save_last=True, every_n_epochs=1
        )

        trainer = Trainer(
            default_root_dir=checkpoint_dir,
            enable_checkpointing=True,
            callbacks=[checkpoint_callback],
            accelerator="gpu",
            devices=num_gpus,
            strategy="ddp",
        )

        # create model
        ...

        trainer.fit(model, data, ...)  # pass in data however needed, e.g. if
                                       # using a datamodule

        model.trainer.save_checkpoint(model_path) # put a final copy of the model
                                                  # at expected output location

        if __name__ == "__main__":
            train_model()


On the curifactory side, it's currently a little annoying to get the correct paths
for input artifacts (this will hopefully change in a couple versions). Essentially
you either need to store the string path directly as an artifact, or you can use
a lazy cacher with ``resolve=True`` (meaning when used as an input, you get access
directly to the ``Lazy`` object, thus the cacher, thus the cacher's ``get_path()``)

An example of how you would set this up in some prior stage:

.. code-block:: python
    :caption: stages/data_setup.py

    import curifactory as cf

    @cf.stage(outputs=[cf.Lazy("dataset", resolve=False)], cachers=[PickleCacher])
    def create_dataset(record: cf.Record):
        ...

Then, to set up a stage to call the external trainer, we collect all the necessary paths
(inputs either directly as the input or by getting the cacher from unresolved lazy instances),
output paths from the record's current ``stage_cachers`` or by outputing a file reference cacher,
and any other side effect paths from the record's ``.get_path()`` or ``.get_dir()``. We construct
the CLI call, and then run it.

.. code-block:: python
    :caption: stages/model.py

    import os
    import curifactory as cf
    from params import Params  # assume this is your ExperimentParameters class

    @cf.stage(["dataset"], ["model_path"], [FileReferenceCacher])
    def externally_train(record: cf.Record, dataset: cf.Lazy):
        params: Params = record.params

        # get all the associated paths

        dataset_path = dataset.cacher.get_path()  # dataset is an unresolved lazy so
                                                  # we get the path from its cacher
        output_model_path = record.get_path("model.ckpt")  # this ensures the model
                                                           # path is tracked
        checkpoint_dir = record.get_dir("model_checkpoints")

        python_cmd = [
            "torchrun",
            "--standalone",  # means we're only using 1 node
            f"--nproc_per_node {params.num_gpus}",
            "--module", "external.my_model_trainer.py",
            "--dataset_path", dataset_path,
            "--model_path", output_model_path,
            "--checkpoint_dir", checkpoint_dir,
            "--num_gpus", str(params.num_gpus),
        ]

        print(*python_cmd)  # it's helpful to print the exact command so you
                            # can separately debug it if needed
        os.system(" ".join(python_cmd))

        return output_model_path


..
    Model checkpoint resuming
    =========================

    TODO


..
    Curifactory pytorch lightning logger
    ====================================

    TODO


..
    Interactive jupyter notebook artifact
    =====================================

    TODO


..
    Using slurm in HPC environments
    ===============================

    TODO


Cachers for Pytorch Lightning models
====================================

Implementing a cacher for a pytorch lightning model can be difficult to make generic
across multiple different model classes. (Mainly because you have to call ``load_from_checkpoint``
on the correct type.)

It's possible to use a cacher's extra metadata to track this type on save, and then manually
condition on it in the load function:

.. code-block:: python

    import pytorch_lighting as pl

    from my_code import ModelType1, ModelType2

    class ModelCacher(cf.caching.Cacheable):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, extension=".ckpt", **kwargs)

        def save(self, obj: pl.LightningModule):
            obj.trainer.save_checkpoint(self.get_path())
            self.extra_metadata["type"] = obj.__class__.__name__
            self.save_metadata()

        def load(self):
            self.load_metadata()
            type_str = self.extra_metadata["type"]

            if type_str == "ModelType1":
                return ModelType1.load_from_checkpoint(self.get_path())
            elif type_str == "ModelType2":
                return ModelType2.load_from_checkpoint(self.get_path())
