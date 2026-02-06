import os
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
