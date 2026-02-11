import sys

import pytest

from curifactory.experimental.cli import main


def test_broken_pipeline_call(test_manager, capfd):
    """Trying to run a pipeline with an error in the file should raise the error,
    not quietly ignore."""
    sys.argv = ["cf", "run", "test.experimental.pipelines.broken.something"]
    main()

    out, err = capfd.readouterr()
    print(out)
    assert (
        'Pipeline module "test.experimental.pipelines.broken.something" failed on import:'
        in out
    )


def test_non_default_pipeline(test_manager, capfd):
    """Trying to run a pipeline by directly specifying module name (not already included in default imports) should run successfully"""

    sys.argv = ["cf", "run", "test.experimental.pipelines.notindefault.valid"]
    main()
    out, err = capfd.readouterr()
    print(out)

    assert "Execution completed" in out
