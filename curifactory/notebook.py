"""Functions for creating experiment jupyter notebooks."""

import logging
import os
import subprocess


def write_experiment_notebook(
    experiment_name,
    param_files,
    param_sets,
    manager,
    path: str,
    directory_change_back_depth: int = 2,
    use_global_cache: bool = None,
    errored: bool = False,
    suppress_global_warning: bool = False,
    leave_script: bool = False,
):
    """Creates a jupyter notebook prepopulated with experiment info and cells to re-run
    the experiment and discover all associated data stored in record states. This function
    is run by the :code:`run_experiment()` function.

    Args:
        experiment_name (str): The name of the run experiment
        param_files (List[str]): List of parameter file names
        param_sets (List[ExperimentParameters]): List of all used ``ExperimentParameters`` from parameter files.
        manager (ArtifactManager): :code:`ArtifactManager` used in the experiment.
        path (str): The path to the directory to store the notebook in.
        directory_change_back_depth (int): How many directories up the notebook needs
            to be in the project root (so imports and cache paths are all correct.)
        use_global_cache (bool): Whether we're using the normal experiment cache or
            a separate specific cache folder (mostly just used to display a warning
            in the notebook.)
        errored (bool): Whether the experiment errored or nat while running, will display
            a warning in the notebook.
        suppress_global_warning (bool): Don't show a warning if :code:`use_global_cache`
            is true.
        leave_script (bool): Don't remove the script that was converted into notebook (this is
            primarily just for testing purposes)
    """
    logging.info("Creating experiment notebook...")

    if use_global_cache is None:
        use_global_cache = not manager.store_full

    output_lines = [
        "# %%",
        "'''",
        f"# {manager.experiment_name} - {manager.experiment_run_number}",
        f"\nExperiment name: **{manager.experiment_name}**  ",
        f"Experiment run number: **{manager.experiment_run_number}**  ",
        f"Run timestamp: **{manager.run_timestamp.strftime('%m/%d/%Y %H:%M:%S')}**  ",
        f"Reference: **{manager.get_reference_name()}**  ",
        f"Git commit: {manager.git_commit_hash}  ",
        f"Param files: {str(manager.parameter_files)}",
        "\n**Parameters**:\n",
    ]

    # output the list of parameters used and assoc hashes
    for key in manager.param_file_param_sets:
        output_lines.append(f"* {key}")
        for name, hash in manager.param_file_param_sets[key]:
            output_lines.append(f"\t* {name} - {hash}")

    output_lines.extend(
        [
            "---",
            "'''",
            "",
        ]
    )

    # pathing for whether full run or not
    directory_change_back = "/".join([".."] * directory_change_back_depth)
    cache_dir_arg = f"manager_cache_path='{manager.get_run_output_path()}', cache_path='{manager.get_run_output_path()}/artifacts', "
    # warn if data is potentially wrong
    if use_global_cache:
        cache_dir_arg = ""
        dry_warning = ""
        if not suppress_global_warning:
            output_lines.extend(
                [
                    "# %%",
                    "'''",
                    "<span style='color: orange;'><b>WARNING - </b></span>Experiment was not run with a `--store-full` flag, and so is simply using the project-wide cache rather than a specific experiment run cache. Any recent experiment runs since this notebook was created may have altered cached data."
                    "'''",
                    "",
                ]
            )
    else:
        dry_warning = "# Note that if this experiment uses lazy artifacts, you will want to remove the `dry=True` args below"

    if errored:
        output_lines.extend(
            [
                "# %%",
                "'''",
                "<span style='color: red;'><b>WARNING - </b></span>This experiment run did not complete due to an exception."
                "'''",
                "",
            ]
        )

    # imports and logger lines
    output_lines.extend(
        [
            "# %%",
            f"%cd {directory_change_back}",
            "",
            "# %%",
            "import logging",
            "from curifactory import ArtifactManager, experiment",
            "",
            "# %%",
            "logger = logging.getLogger()",
            "logger.setLevel(logging.INFO)",
            "",
            "# %%",
            dry_warning,
            f'manager = ArtifactManager("{experiment_name}", {cache_dir_arg} dry=True)',
            f'experiment.run_experiment("{experiment_name}", {str(param_files)}, dry=True, mngr=manager)',
            "",
            "# %%",
        ]
    )

    for i, param in enumerate(manager.records):
        output_lines.extend(
            [
                f"records{i} = manager.records[{i}]",
                f"state{i} = manager.records[{i}].state",
            ]
        )

        if manager.records[i].params is not None:
            output_lines.extend(
                [
                    f'print("state{i} - (" + records{i}.params.name + ") stages: " + str(records{i}.stages))',
                    f'print("keys: " + str(state{i}.keys()) + "\\n")',
                ]
            )
        else:
            output_lines.extend(
                [
                    f'print("state{i} - ((aggregate record)) stages: " + str(records{i}.stages))',
                    f'print("keys: " + str(state{i}.keys()) + "\\n")',
                ]
            )
        output_lines.append("")

    script_path = path + ".py"
    notebook_path = path + ".ipynb"

    output_lines = [line + "\n" for line in output_lines]

    with open(script_path, "w") as outfile:
        outfile.writelines(output_lines)

    # run ipynb-py-convert
    logging.info("Converting...")
    # utils.get_command_output(["ipynb-py-convert", script_path, notebook_path])

    cmd_array = ["ipynb-py-convert", script_path, notebook_path]
    print(*cmd_array)
    with subprocess.Popen(
        cmd_array, stderr=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1, text=True
    ) as p:
        for line in p.stdout:
            print(line, end="")  # process line here
        for line in p.stderr:
            print(line, end="")  # process line here
    logging.info("Output experiment notebook at %s", notebook_path)

    if not leave_script:
        os.remove(script_path)
