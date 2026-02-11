import sys

import pytest

from curifactory.experimental.cli import main


def test_db_not_broken_after_failed_pipeline(test_manager, capfd):
    """A failed pipeline shouldn't cripple the database with null IDs etc."""

    sys.argv = ["cf", "run", "test.experimental.pipelines.notindefault.invalid"]
    main()
    out, err = capfd.readouterr()
    print(out)

    sys.argv = ["cf", "run", "test.experimental.pipelines.notindefault.valid"]
    main()
    out, err = capfd.readouterr()
    print(out)

    assert "Execution completed" in out
