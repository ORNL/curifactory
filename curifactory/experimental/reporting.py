"""Classes for handling reporting - adding customizable pieces of information
to an HTML experiement run report.

This is handled through a base ``Reportable`` class, and each reporter class
extends it.
"""


class Reportable:
    """The base reporter class, any custom reporter should extend this.

    Args:
        name (str): A (optional) reference name to give this piece of reported info, it is used
            as the title string suffix. If ``None`` is supplied, it will be suffixed with the
            number of the reportable.
        group (str): An optional string to use for grouping multiple related reportables
            together in the report. By default, all reportables are ordered by record. This
            will create a separate entry on the TOC and put them next to each other in the
            report.

    Note:
        When subclassing a reportable, ``html()`` must be overriden, and ``render()``
        optionally may be depending on the nature of the reportable. If a reportable relies on
        some form of external file, such as an image or figure, implement ``render()`` to save
        it (using this class's ``path`` variable as the directory), and then reference it
        in the output from ``html()``. The internal reporting mechanisms handle calling
        both of these functions as needed.

        A simplified example of the ``FigureReporter`` is shown here:

        .. code-block:: python

            class FigureReporter(Reportable):
                def __init__(self, fig, name=None, group=None):
                    self.fig = fig
                    super().__init__(name=name, group=group)

                def render(self):
                    self.fig.savefig(os.path.join(self.path, f"{self.qualified_name}.png"))

                def html(self):
                    return f"<img src='{self.path}/{self.qualified_name}.png'>"
    """

    def __init__(self, name=None, group=None):
        self.rendered: bool = False
        """A flag indicating whether this reportable's :code:`render()` has been called yet or not."""
        self.path: str = ""
        """Set internally by reporting functions, this variable holds a valid path where a
        reportable can save files (e.g. images) as needed. This is available to access both
        in :code:`render()` and :code:`html()`"""
        self.name: str = name
        """The suffix to title the reportable with. NOTE: if a custom reportable is saving anything
        in a render function, don't use just name in the path. ``self.qualified_name`` should be
        preferred, as it is the fully prefixed name."""
        self.qualified_name: str = name
        """The full prefixed name including the stage name and aggregate indicator. This is
        set by the record when a ``report()`` is called."""
        self.group: str = group
        """If specified, reports group all reportables with the same ``group`` value together."""
        # self.record = None
        """Record: The record this reportable came from, automatically populated via ``record.report()``"""
        # self.stage: str = ""
        # """The name of the stage this reportable comes from, used as part of the title."""
        # self.stage = None
        self.artifact = None

    def __getstate__(self):
        # avoid pickling the container artifact and stage etc.
        return {k: v for (k, v) in self.__dict__.items() if k not in ["artifact"]}

    @property
    def html(self):
        return self.get_html()

    def get_html(self) -> str | list[str]:
        """When a report is created, the ``html()`` function for every reportable is
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

    def __init__(
        self, html_string: str | list[str], name: str = None, group: str = None
    ):
        self.html_string = html_string
        """The raw string of HTML to include."""
        super().__init__(name=name, group=group)

    def get_html(self) -> str | list[str]:
        return self.html_string
