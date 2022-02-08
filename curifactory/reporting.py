"""Classes for handling reporting - adding customizable pieces of information
to an HTML experiement run report.

This is handled through a base :code:`Reportable` class, and each reporter class
extends it.
"""

from dataclasses import asdict
import datetime
import json
import logging
import os
import shutil
from typing import List

import matplotlib.pyplot as plt
import numpy as np

from graphviz import Digraph
from graphviz.backend import ExecutableNotFound
import pandas as pd

from curifactory import utils


COLORS = [
    "darkseagreen2",  # #b4eeb4
    "thistle",
    "peachpuff",
    "paleturquoise2",
    "salmon",
    "silver",
    "hotpink",
    "deepskyblue",
    "yellowgreen",
]

COLOR_VALS = {  # because apparently some of graphviz color names aren't websafe
    "darkseagreen2": "#b4eeb4",
    "thistle": "#d8bfd8",
    "peachpuff": "#ffdab9",
    "paleturquoise2": "#aeeeee",
    "salmon": "#fa8072",
    "silver": "#c0c0c0",
    "hotpink": "#ff69b4",
    "deepskyblue": "#00bfff",
    "yellowgreen": "#9acd32",
}


class Reportable:
    """The base reporter class, any custom reporter should extend this.

    Args:
        name (str): A (optional) reference name to give this piece of reported info, it is used
            as the title string suffix. If :code:`None` is supplied, it will be suffixed
            with the number of the reportable.
        group (str): An optional string to use for grouping multiple related reportables
            together in the report. By default, all reportables are ordered by record. This
            will create a separate entry on the TOC and put them next to each other in the
            report.

    Note:
        When subclassing a reportable, :code:`html()` must be overriden, and :code:`render()`
        optionally may be depending on the nature of the reportable. If a reportable relies on
        some form of external file, such as an image or figure, implement :code:`render()` to save
        it (using this class's :code:`path` variable as the directory), and then reference it
        in the output from :code:`html()`. The internal reporting mechanisms handle calling
        both of these functions as needed.

        A simplified example of the :code:`FigureReporter` is shown here:

        .. code-block:: python

            class FigureReporter(Reportable):
                def __init__(self, fig, name=None, group=None):
                    self.fig = fig
                    super().__init__(name=name, group=group)

                def render(self):
                    self.fig.savefig(os.path.join(self.path, f"{self.name}.png"))

                def html(self):
                    return f"<img src='{self.path}/{self.name}.png'>"
    """

    def __init__(self, name=None, group=None):
        self.rendered: bool = False
        """A flag indicating whether this reportable's :code:`render()` has been called yet or not."""
        self.path: str = ""
        """Set internally by reporting functions, this variable holds a valid path where a
        reportable can save files (e.g. images) as needed. This is available to access both
        in :code:`render()` and :code:`html()`"""
        self.name: str = name
        """The suffix to title the reportable with."""
        self.group: str = group
        """If specified, reports group all reportables with the same :code:`group` value together."""
        self.record = None
        """Record: The record this reportable came from, automatically populated via :code:`record.report()`"""
        self.stage: str = ""
        """The name of the stage this reportable comes from, used as part of the title."""

    def html(self):
        """When a report is created, the :code:`html()` function for every reportable is
        called and appended to the report. This function should either return a single
        string of html, or can return a list of lines of html.

        Note:
            Any subclass is **required** to implement this.
        """
        pass

    def render(self):
        """Any file outputs or calculations that should only run once go here."""
        pass


class HTMLReporter(Reportable):
    """Adds the raw string of HTML passed to it to the report.

    Args:
        html_string (str): The raw string of HTML to include.

    Example:
        .. code-block:: python

            @stage(...)
            def report_hello(record: Record ,...):
                record.report(HTMLReporter("<h1>Hello world!</h1>"))

    """

    def __init__(self, html_string, name=None, group=None):
        self.html_string = html_string
        """The raw string of HTML to include."""
        super().__init__(name=name, group=group)

    def html(self):
        return self.html_string


class DFReporter(Reportable):
    """Adds an HTML table to the report for the given pandas dataframe.

    Args:
        df (pd.DataFrame): The pandas dataframe to include in the report.
        float_prec (int): the floating point precision to round all values to.

    Note:
        If you need to use any of the pandas stylers, apply them and pass :code:`df.render()` to
        an :code:`HTMLReporter` instead.
    """

    def __init__(self, df: pd.DataFrame, name=None, group=None, float_prec=4):
        self.df = df
        self.float_prec = float_prec
        super().__init__(name=name, group=group)

    # def html(self):
    #     with pd.option_context("display.precision", self.float_prec, 'display.max_columns', 500, 'display.max_columns')
    #     pd.set_option("display.precision", self.float_prec)

    # def render(self):
    #     # doing this so easily browsable in excel
    #     self.df.to_csv(f"{self.path}{self.name}.csv")

    def html(self):
        output = ["<table border='1' cellspacing='0'><tr><th></th>"]

        # column row
        for col in self.df.columns:
            output.append(f"<th>{col}</th>")

        output.append("</tr>")

        for index, row in self.df.iterrows():
            output.append("<tr>")
            output.append(f"<th>{index}</th>")

            for item in row:
                if (
                    type(item) == float
                    or type(item) == np.float64
                    or type(item) == np.float32
                ):
                    output.append(
                        "<td align='right'><pre>{0:.{1}f}</pre></td>".format(
                            item, self.float_prec
                        )
                    )
                else:
                    output.append(f"<td align='right'><pre>{item}</pre></td>")
            output.append("</tr>")

        output.append("</table>")
        return output


class JsonReporter(Reportable):
    """Adds an indented JSON dump in a :code:`<pre>` tag for a passed dictionary.

    Args:
        dictionary (Dict): The python dictionary to write to a JSON string.
    """

    def __init__(self, dictionary, name=None, group=None):
        self.data = dictionary
        super().__init__(name=name, group=group)

    def html(self):
        return [
            "<pre>",
            json.dumps(self.data, indent=4, default=lambda x: str(x)),
            "</pre>",
        ]


class FigureReporter(Reportable):
    """Adds a passed matplotlib figure to the report.

    Args:
        fig: A matplotlib figure to render.
        kwargs: All keywords args are passed to the figures :code:`savefig()` call in render.
    """

    def __init__(self, fig, name=None, group=None, **kwargs):
        self.kwargs = kwargs
        self.fig = fig
        super().__init__(name=name, group=group)

    def render(self):
        if "format" not in self.kwargs:
            self.kwargs["format"] = "png"
        self.fig.savefig(
            f"{self.path}/{self.name}.{self.kwargs['format']}", **self.kwargs
        )

    def html(self):
        return f"<img src='{self.path}/{self.name}.{self.kwargs['format']}'>"


class LinePlotReporter(Reportable):
    """Takes set(s) of data, creates matplotlib line plots for it, and adds to the report.

    There are several ways to use this reportable, x (optional) and y are both either a single
    list/numpy array of data, or are both dictionaries of lists/numpy arrays of data to plot.

    Possible combinations:

    * Passing a single list/numpy array of only y data
    * Passing a single list/numpy array of y and x data
    * Passing a dictionary (where keys appear in the legend) of lists/numpy arrays of y data, each to be plotted as its own line.
    * Passing a dictionary (where keys appear in the legend) of lists/numpy arrays of both y and x data, each to be plotted as its own line.

    Args:
        y: a single list/numpy array or dictionary of lists/numpy arrays of y data.
        x: (optional), a single list/numpy array or dictionary of lists/numpy arrays of x data.
            If specified, this must match y.
        plot_kwargs (Dict): The **kwargs to pass to the matplotlib :code:`plt.plot()` call.
        savefig_kwargs (Dict): The **kwargs to pass to the :code:`fig.savefig()` call on render.

    Example:
        .. code-block:: python

            @stage(...)
            def report_results(record: Record, ...):

                train_loss = [0.8, 0.7, 0.6]
                test_loss = [0.5, 0.3, 0.4]
                acc = [.93, 0.95, 0.96]

                record.report(LinePlotReporter(
                    y={
                        "Training loss": train_loss,
                        "Testing loss": test_loss,
                        "Accuracy": acc
                    },
                    name="training_history"))

        The above block will result in the following graph added to the report:

        .. figure:: line_plot_reporter_example.png
            :align: center
    """

    def __init__(
        self, y, x=None, name=None, group=None, plot_kwargs={}, savefig_kwargs={}
    ):
        self.savefig_kwargs = savefig_kwargs
        self.plot_kwargs = plot_kwargs
        self.y = y
        self.x = x
        super().__init__(name=name, group=group)

    def render(self):
        plt.figure(facecolor="white")

        if self.x is None:
            if isinstance(self.y, dict):
                for key in self.y:
                    plt.plot(self.y[key], label=key, **self.plot_kwargs)
                plt.legend()
            else:
                plt.plot(self.y, **self.plot_kwargs)
        else:
            if isinstance(self.y, dict):
                for key in self.y:
                    plt.plot(self.x[key], self.y[key], label=key, **self.plot_kwargs)
            else:
                plt.plot(self.x, self.y, **self.plot_kwargs)
        plt.grid(True)

        fig = plt.gcf()
        if "format" not in self.savefig_kwargs:
            self.savefig_kwargs["format"] = "png"
        fig.savefig(
            f"{self.path}/{self.name}.{self.savefig_kwargs['format']}",
            **self.savefig_kwargs,
        )
        plt.close()

    def html(self):
        return f"<img src='{self.path}/{self.name}.{self.savefig_kwargs['format']}'>"


def render_report_head(manager) -> List[str]:
    """Generates the report head tag."""
    return [
        f"<head><title>{manager.experiment_name}/{manager.experiment_run_number}</title>",
        "<link rel='stylesheet' href='style.css'></head>",
    ]


def render_report_info_block(manager) -> List[str]:
    """Generate the header and block of metadata at the top of the report."""

    html_lines = []

    status_color = ""
    if manager.status == "incomplete":
        status_color = "orange"
    elif manager.status == "complete":
        status_color = "green"
    elif manager.status == "error":
        status_color = "red"
    elif manager.status == "LIVE":
        status_color = "cyan"
    status_line = (
        f"<b><span style='color: {status_color}'>{manager.status.upper()}</span></b>"
    )
    if manager.status == "error":
        status_line += " - " + manager.error
    if manager.interactive:
        status_line += " - (interactive session)"

    html_lines.append(
        f"<h1 id='title'>Report: {manager.experiment_name} - {manager.experiment_run_number}</h1>"
    )
    html_lines.extend(
        [
            "<div id='experiment-info-block'>",
            f"<p>Experiment name: <b>{manager.experiment_name}</b> </br>",
            f"Experiment run number: <b>{manager.experiment_run_number}</b></br>",
            f"Run timestamp: <b>{manager.run_timestamp.strftime('%m/%d/%Y %H:%M:%S')}</b></br>",
            f"Reference: <b>{manager.get_reference_name()}</b></br>",
            f"Hostname: <b>{manager.hostname}</b></br>",
            f"Run status: {status_line}</br>",
            f"Git commit: {manager.git_commit_hash}</br>",
            f"Params files: {str(manager.experiment_args_file_list)}</br></p>",
            "<ul>",
        ]
    )
    # output the list of parameters used and assoc hashes
    handled_hashes = []
    for key in manager.experiment_args:
        html_lines.append(f"<li>{key} <ul>")
        for name, args_hash in manager.experiment_args[key]:
            html_lines.append(f"<li>{name} - {args_hash}</li>")
            handled_hashes.append(args_hash)
        html_lines.append("</ul></li>")
    handled_non_params_header = (
        False  # did we print out a header for non-file based params yet?
    )
    for argset in manager.get_all_argsets():
        if argset.hash not in handled_hashes:
            if not handled_non_params_header:
                html_lines.append("<li>Non-file (live) argsets <ul>")
                handled_non_params_header = True
            html_lines.append(f"<li>{argset.name} - {argset.hash}</li>")
    if handled_non_params_header:
        html_lines.append("</ul></li>")

    html_lines.append("</ul></div>")

    if manager.status == "LIVE":
        # TODO: (37/26/2022) allow suppression if notebook=true passed so can render in notebook without error?
        html_lines.append(
            "<p><span style='color: orange;'><b>WARNING - </b></span>This report was not generated from an experiment script. If generated from an interactive environment, curifactory has no method to reproduce.</p>"
        )
        html_lines.append(
            f"<p id='run-string'>Run string: <pre>{manager.run_line}</pre></p>"
        )

        if manager.store_entire_run:
            store_entire_run_path = os.path.join(
                manager.runs_path, manager.get_reference_name()
            )
            html_lines.append(
                f"<p><span style='color: green'><b>This run has a full cache store.</b></span> Live runs have a much lower chance of reproducing correctly than an experiment script, but you can utilize this cache with:"
                f'<pre>manager = ArtifactManager("{manager.experiment_name}", cache_path="{store_entire_run_path}", dry_cache=True)</pre></p>'
            )
    else:
        html_lines.append(
            f"<p id='run-string'>Run string: <pre>{manager.run_line}</pre></p>"
        )

        if manager.store_entire_run:
            html_lines.append(
                f"<p><span style='color: green'><b>This run has a full cache store.</b></span> Reproduce with:"
                f"<pre>{manager.reproduction_line}</pre></p>"
            )

    if manager.notes is not None and manager.notes is not None and manager.notes != "":
        html_lines.append("<h3>Notes</h3>")
        notes = manager.notes
        notes = notes.replace("\n", "</br>")
        html_lines.append(f"<p>{notes}</p>")

    return html_lines


def render_report_toc() -> List[str]:
    """Render table of contents for the overall report."""
    return [
        "<a name='top'></a>" "<h2>Table of Contents</h2>",
        "<ul id='toc'>",
        "<li><a href='#reportables'>Reportables</a></li>"
        "<li><a href='#map'>Map</a></li>",
        "<li><a href='#stage_detail'>Stage Detail</a></li>",
        "<li><a href='#args'>Args</a></li>",
        "</ul>",
    ]


def render_report_reportables_toc(manager) -> List[str]:
    """Render the table of contents for the reportables."""
    html_lines = []

    # TODO: (01/27/2022) we can do this just by getting None group in grouped.
    # (will have to modify get_grouped_reportables to include None)
    non_grouped_reportables = manager.get_ungrouped_reportables()
    grouped_reportables = manager.get_grouped_reportables()

    html_lines.append("<a name='reportables'></a>")
    html_lines.append("<h2>Reportables</h2><ul id='reportables-list'>")
    for group in grouped_reportables:
        html_lines.append(f"<li>{group}<ul>")
        for reportable in grouped_reportables[group]:
            html_lines.append(
                f"<li><a href='#{reportable.name}'>{reportable.name}</a></li>"
            )
        html_lines.append("</ul></li>")
    for reportable in non_grouped_reportables:
        html_lines.append(
            f"<li><a href='#{reportable.name}'>{reportable.name}</a></li>"
        )
    html_lines.append("</ul>")
    return html_lines


def render_report_all_reportables(
    manager,
    reportables_path: str,
    override_display_path: str = None,
    notebook: bool = False,
) -> List[str]:
    """Get the HTML for displaying all reportables output."""
    html_lines = []

    non_grouped_reportables = manager.get_ungrouped_reportables()
    grouped_reportables = manager.get_grouped_reportables()

    # render grouped reportables
    for group in grouped_reportables:
        html_lines.append(f"<h3 class='reportable-group-title'>{group}</h3>")
        for reportable in grouped_reportables[group]:
            html_lines.extend(
                render_reportable(
                    reportable,
                    manager,
                    reportables_path,
                    override_display_path,
                    notebook,
                )
            )

    # render all non-grouped reportables
    for reportable in non_grouped_reportables:
        html_lines.extend(
            render_reportable(
                reportable, manager, reportables_path, override_display_path, notebook
            )
        )

    return html_lines


def render_report_stage_map(manager, graphs_path) -> List[str]:
    """Generate and write out the graphviz graph for the stages and return the html to display it."""
    graph = map_full_svg(manager)
    with open(f"{graphs_path}/full.gv", "w") as outfile:
        outfile.write(graph.source)

    html_lines = []
    html_lines.append("<a name='map'></a>")
    html_lines.append("<h2>Process/Stages Map</h2>")
    html_lines.append("<p><a href='#top'>back to top</a></p>")
    html_lines.append(render_graph(graph))
    return html_lines


def render_report_detailed_stage_maps(manager, graphs_path) -> List[str]:
    """Generate and write out a more detailed graphviz graph for each record and return the html."""
    html_lines = []
    html_lines.append("<a name='stage_detail'></a>")
    html_lines.append("<h2>Stage Data Detail</h2>")
    html_lines.append("<p><a href='#top'>back to top</a></p>")

    for index, record in enumerate(manager.records):
        graph = map_single_svg(manager, record)
        with open(f"{graphs_path}/record_{index}.gv", "w") as outfile:
            outfile.write(graph.source)
        html_lines.append(render_graph(graph))

    html_lines.append("<a name='args'></a>")
    html_lines.append("<h2>Args</h2>")
    html_lines.append("<p><a href='#top'>back to top</a></p>")
    return html_lines


def render_report_argset_dump(manager) -> List[str]:
    """Dump out the JSON for all args used by manager."""
    html_lines = []

    argsets = manager.get_all_argsets()
    for argset in argsets:
        name = argset.name
        args_hash = argset.hash
        html_lines.append(f"<h4>{name} - {args_hash}</h4>")
        html_lines.append("<pre>")

        def stringify(x):
            # make html-safe
            return str(x).replace("<", "&lt;").replace(">", "&gt;")

        argset_data = asdict(argset)
        del argset_data["name"]
        del argset_data["overwrite"]
        del argset_data["hash"]
        html_lines.append(json.dumps(argset_data, indent=2, default=stringify))
        html_lines.append("</pre>")

    return html_lines


def prepare_report_path(output_path, report_name):
    """Set up any necessary folders for a report at the given location. This will not error if the location already has a report in it, but will remove existing reportables and graphs."""

    folder_path = os.path.join(output_path, report_name)
    logging.info("Preparing report path '%s'..." % folder_path)

    graphs_path = os.path.join(folder_path, "graphs")
    reportables_path = os.path.join(folder_path, "reportables")

    if os.path.exists(graphs_path):
        shutil.rmtree(graphs_path)
    if os.path.exists(reportables_path):
        shutil.rmtree(reportables_path)

    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    os.mkdir(graphs_path)
    os.mkdir(reportables_path)

    return folder_path, graphs_path, reportables_path


def run_report(manager, output_path, name, css_path=None):
    """Generate a full HTML report for the given manager and passed argsets.

    Args:
        manager (ArtifactManager): The manager to base the graph off of.
        output_path (str): The string path to the root directory of where you want the report stored.
        name (str): The name to store this report under (will generate a folder of this name in the
            output_path.
        css_path (str): The path to a css file to use for styling the report. (This file will get
            copied into the output_path/name folder.)
    """

    # TODO: (01/26/2022) in principle this is where we could check manager if stored, and store if not.

    folder_path, graphs_path, reportables_path = prepare_report_path(output_path, name)

    html_lines = ["<html>"]
    html_lines.extend(render_report_head(manager))
    html_lines.append("<body>")
    html_lines.extend(render_report_info_block(manager))
    html_lines.extend(render_report_toc())

    # render reportables
    if len(manager.reportables) > 0:
        html_lines.extend(render_report_reportables_toc(manager))
        html_lines.extend(render_report_all_reportables(manager, reportables_path))

    # render graphs
    html_lines.extend(render_report_stage_map(manager, graphs_path))
    html_lines.extend(render_report_detailed_stage_maps(manager, graphs_path))

    # output the JSON args for each argset
    html_lines.extend(render_report_argset_dump(manager))
    html_lines.append("</body></html>")

    # write out all the things!
    with open(f"{folder_path}/index.html", "w") as outfile:
        outfile.writelines(html_lines)

    with open(f"{folder_path}/run_info.json", "w") as outfile:
        json.dump(manager.run_info, outfile, indent=4)

    if css_path is not None:
        if not os.path.exists(css_path):
            logging.warning("Reports CSS file %s not found" % css_path)
        else:
            shutil.copyfile(css_path, f"{folder_path}/style.css")

    return folder_path, graphs_path, reportables_path


def _add_record_subgraph(dot, record_index, record, manager, detailed=True):
    with dot.subgraph(name=f"cluster_{record_index}") as c:
        c.attr(color=str(_get_color(record_index)))
        c.attr(style="filled")
        if record.args is not None:
            c.attr(
                label="record "
                + str(record_index)
                + "\\nargs: "
                + str(record.args.name)
            )
        else:
            c.attr(label="record " + str(record_index) + "\\nargs: None")
        for stage in record.stages:
            stage_name = f"{record_index}_{stage}"
            c.node(stage_name, stage, style="filled", fillcolor="white", fontsize="12")

        for index, artifact in enumerate(manager.artifacts):
            if artifact.init_record == record:
                if detailed:
                    table = (
                        "<<table border='0' cellborder='1' cellspacing='0'><tr><td>"
                        + "<b>"
                        + str(artifact.name)
                        + "</b>"
                        + "</td></tr><tr><td width='0'>"
                        + artifact.html_safe()
                        + "</td></tr><tr><td>"
                        + artifact.file
                        + "</td></tr></table>>"
                    )
                    c.node(
                        f"a{index}",
                        table,
                        shape="none",
                        fontsize="8",
                        padding="0",
                        margin="0",
                        width="0",
                    )
                else:
                    c.node(
                        f"a{index}",
                        str(artifact.name),
                        shape="rectangle",
                        fontsize="10",
                        height=".20",
                    )

        for index, input_set in enumerate(record.stage_inputs):
            for input_index in input_set:
                if input_index != -1:
                    dot.edge(
                        f"a{input_index}",
                        f"{record_index}_{record.stages[index]}",
                        arrowsize=".65",
                    )
        for index, output_set in enumerate(record.stage_outputs):
            for output_index in output_set:
                dot.edge(
                    f"{record_index}_{record.stages[index]}",
                    f"a{output_index}",
                    arrowsize=".65",
                )


def update_report_index(experiments_path, reports_root_dir):
    """Generate a nice index.html with a summary line for each experiment run report in the
    passed directory.

    Args:
        experiments_path (str): The path to where the experiment scripts are, used to get any top
            experiment description comments from the file.
        reports_root_dir (str): The directory containing the report folders. This is where the output
            index.html is placed.
    """
    logging.info("Updating report index...")

    runs = []
    experiment_runs = {}

    no_info_runs = []
    no_index_runs = []
    informal_runs = (
        []
    )  # this is a combo of both no_info and no_index, they get listed together but distinguishing them to construct links differently is important

    # gather all reports
    for filename in os.listdir(reports_root_dir):
        if filename == "_latest":
            continue

        full_filename = f"{reports_root_dir}/{filename}"
        if not os.path.isdir(full_filename):
            continue

        if os.path.exists(f"{full_filename}/run_info.json"):
            with open(f"{full_filename}/run_info.json", "r") as infile:
                info = json.load(infile)

                info["order_timestamp"] = datetime.datetime.strptime(
                    info["timestamp"], utils.TIMESTAMP_FORMAT
                )

                runs.append(info)
                experiment_name = info["experiment_name"]
                if experiment_name not in experiment_runs:

                    # try to get comment on experiment
                    comment = ""
                    try:
                        with open(
                            f"{experiments_path}/{experiment_name}.py", "r"
                        ) as infile:
                            lines = infile.readlines()
                            comment = utils.get_py_opening_comment(lines)
                    except:  # noqa: E722 -- there's not really any need to handle this, either we get the comment or we don't.
                        pass

                    experiment_runs[experiment_name] = {"runs": [], "comment": comment}

                experiment_runs[experiment_name]["runs"].append(info)
        elif os.path.exists(f"{full_filename}/index.html"):
            informal_runs.append(filename)
            no_info_runs.append(filename)
        else:
            informal_runs.append(filename)
            no_index_runs.append(filename)

    logging.info("    %s labeled reports found", str(len(runs)))
    logging.info("    %s informal runs found", str(len(informal_runs)))

    html = [
        "<html>",
        "<head><title>Reports Index</title>",
        "<link rel='stylesheet' href='style.css'></head>",
        "<body>",
        "<h1 id='title'>Reports</h1>",
        "<p><a href='_latest/index.html'>View latest report</a></p>",
    ]

    # experiment_index =
    html.extend(["<h2>Experiments</h2>", "<ul>"])
    for experiment in experiment_runs:
        html.append(f"<li><a href='#{experiment}'>{experiment}</a></li>")
    html.append("<li><a href='#ALL'>ALL RUNS</a></li>")
    html.append("</ul>")

    for experiment in experiment_runs:
        html.extend(
            [
                f"<a name='{experiment}'></a>",
                f"<h2>{experiment}</h2>",
                f"<p>{experiment_runs[experiment]['comment']}</p>",
            ]
        )

        # order the runs
        ex_runs = sorted(
            experiment_runs[experiment]["runs"],
            key=lambda i: i["order_timestamp"],
            reverse=True,
        )

        html.append("<ul>")
        for run in ex_runs:
            html.append(_get_run_index_line(run))
        html.append("</ul>")

    html.extend(["<a name='ALL'></a>", "<h2>All labeled runs</h2>"])

    runs = sorted(runs, key=lambda i: i["order_timestamp"], reverse=True)
    html.append("<ul>")
    for run in runs:
        html.append(_get_run_index_line(run))
    html.append("</ul>")

    html.append("<h2>Informal runs</h2>")
    html.append("<ul>")
    for filename in informal_runs:
        if filename in no_info_runs:
            html.append(f"<li><a href='{filename}/index.html'>{filename}</a></li>")
        elif filename in no_index_runs:
            html.append(f"<li><a href='{filename}'>{filename}</a> (NO REPORT)</li>")
    html.append("</ul>")

    with open(f"{reports_root_dir}/index.html", "w") as outfile:
        outfile.writelines(html)


def map_single_svg(manager, record, detailed=True, colors=None):
    """Create a graphviz dot graph of the stages/artifacts for the given record.

    Args:
        manager (ArtifactManager): the manager to base the graph off of.
        record (Record): The specific record to make the graph for.
        detailed (bool): Whether to include artifact preview and caching information or not.
        colors: A list or dictionary of colors to use if you wish to override the default.

    Important:
        For this function to run successfully, graphviz must be installed.
    """
    _assign_colors(colors)

    dot = Digraph()
    dot.attr(compound="true")
    dot.attr(nodesep=".2")
    dot.attr(ranksep=".2")

    for index, record_check in enumerate(manager.records):
        if record_check == record:
            _add_record_subgraph(dot, index, record, manager, detailed)

    dot.format = "svg"
    return dot


def map_full_svg(manager, detailed=False, colors=None):
    """Create a graphviz dot graph for the entire experiment. (Maps out each stage and
    the input/output artifacts for each.)

    Args:
        manager (ArtifactManager): the manager to base the graph off of.
        detailed (bool): Whether to include artifact preview and caching information or not.
        colors: A list or dictionary of colors to use if you wish to override the default.

    Important:
        For this function to run successfully, graphviz must be installed.
    """
    _assign_colors(colors)

    dot = Digraph()
    dot.attr(compound="true")
    dot.attr(fontsize="10")
    dot.attr(nodesep=".15")
    dot.attr(ranksep=".15")
    # dot.attr(rankdir='LR')

    for index, record in enumerate(manager.records):
        _add_record_subgraph(dot, index, record, manager, detailed)

    # add record connections to any aggregate stages
    for index, record in enumerate(manager.records):
        for prev_record in record.input_records:
            if prev_record == record:
                continue
            # prev_record_index =
            for jndex, manager_record in enumerate(manager.records):
                if manager_record == prev_record:
                    dot.edge(
                        f"{jndex}_{manager.records[jndex].stages[-1]}",
                        f"{index}_{record.stages[0]}",
                        ltail=f"cluster_{jndex}",
                    )

    dot.format = "svg"
    return dot


def _assign_colors(colors=None):
    global COLORS, COLOR_VALS

    if colors is not None:
        if not isinstance(colors, list):
            colors = [colors]
        if isinstance(colors[0], tuple):
            COLORS = [color[0] for color in COLORS]
            COLOR_VALS = {color[0]: color[1] for color in COLORS}
        COLORS = colors


def _get_color(index):
    index = index % len(COLORS)
    name = COLORS[index]
    if name in COLOR_VALS:
        return COLOR_VALS[name]
    else:
        return name


def render_graph(graph):
    """Attempts to return the unicode text for the graph svg."""
    try:
        # return graph.pipe().decode('utf-8')
        return graph.pipe().decode("ascii")
    except ExecutableNotFound:
        logging.error(
            "Graphviz not installed, if using conda try 'conda install python-graphviz'."
        )
        return "<p style='color: red'>No graphviz executable found, cannot render stage maps.</p>"
    except Exception as e:
        logging.error("Graphviz error: %s", e)
        return f"<p style='color: red'>{e}</p>"


def render_reportable(
    reportable: Reportable,
    manager,
    reportables_path: str,
    override_display_path: str = None,
    notebook: bool = False,
) -> List[str]:
    """Render a reportable to file and get the HTML to display it."""
    html_lines = []

    # get associated record index
    color_string = "<span style='background-color: "
    for index, record in enumerate(manager.records):
        if record == reportable.record:
            color_string += _get_color(index) + "'>&nbsp;&nbsp;&nbsp;&nbsp;</span>"

    reportable.path = reportables_path  # path relative to experiment for saving
    reportable.render()
    if override_display_path is not None:
        reportable.path = override_display_path
    else:
        reportable.path = "reportables"  # path relative to html report for displaying
    if notebook:
        html_lines.append(
            "<div class='reportable' style='border: 1px solid gray; display: inline-block; vertical-align: top; padding: 5px; padding-top: 0px; padding-bottom: 0px; margin: 5px;'>"
        )
    else:
        html_lines.append("<div class='reportable'>")
    html_lines.append(f"<a name='{reportable.name}'></a>")
    html_lines.append(f"<h3>{reportable.name} {color_string}</h3>")
    reportable_html = reportable.html()
    if isinstance(reportable_html, list):
        html_lines.extend(reportable_html)
    else:
        html_lines.append(reportable_html)
    if not notebook:
        html_lines.append("<p><a href='#reportables'>back to reportables</a></p>")
    html_lines.append("</div>")

    return html_lines


def _get_run_index_line(run):
    desc_line = "<li>"

    if run["status"] == "complete":
        desc_line += "<span style='background-color: green'>&nbsp;&nbsp;</span>"
    elif run["status"] == "incomplete":
        desc_line += "<span style='background-color: orange'>&nbsp;&nbsp;</span>"
    elif run["status"] == "error":
        desc_line += "<span style='background-color: red'>&nbsp;&nbsp;</span>"
    elif run["status"] == "LIVE":
        desc_line += "<span style='background-color: cyan'>&nbsp;&nbsp;</span>"

    desc_line += f" <a href='{run['reference']}/index.html'>{run['reference']}</a> "

    if "hostname" in run:
        desc_line += f"[{run['hostname']}] "

    if run["status"] == "error":
        desc_line += f"<span style='color: red'>{run['error']}</span> "

    if run["full_store"]:
        desc_line += "<span style='color: magenta'><b>(full store)</b></span> "

    if "--dry-cache" in run["cli"] and "--cache" in run["cli"]:
        desc_line += "<span style='color: cyan'><b>(from stored)</b></span> "

    # params
    for params in run["args"]:
        args = [pair[0] for pair in run["args"][params]]
        desc_line += f"<b>{params}</b>({','.join(args)}) "

    # add notes if applicable
    if "notes" in run and run["notes"] is not None and run["notes"] != "":
        shortform_notes = run["notes"]
        if "\n" in shortform_notes:
            shortform_notes = shortform_notes[: shortform_notes.index("\n")]
        desc_line += f"</br><span style='color: #444; font-size: 10pt; font-style: italic;'>{shortform_notes}</span>"

    # add the runline
    desc_line += f"</br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style='color: #a0a0a0; font-family: monospace'>{run['cli']}</span>"

    desc_line += "</li>"

    return desc_line
