import logging
import os

from curifactory import utils


def test_init_logging_creates_missing_log_dir(tmp_path):
    """init_logging should create the log file's parent directory when it
    doesn't exist yet, rather than raising FileNotFoundError. See issue #85."""

    log_path = os.path.join(str(tmp_path), "missing_dir", "run.log")
    assert not os.path.exists(os.path.dirname(log_path))

    utils.init_logging(log_path=log_path, quiet=True)

    assert os.path.exists(log_path)

    # release the file handler so tmp_path cleanup doesn't trip
    logging.getLogger().handlers = []


def test_command_output_does_not_print_to_stdout(capfd):
    """Running a command via get_command_output should only return the
    output string, not actually write to stdout."""

    utils.get_command_output(["git", "rev-parse", "HEAD"])

    out, err = capfd.readouterr()
    assert out == ""
    assert err == ""


def test_command_output_does_not_print_to_stderr(capfd):
    """Running a command via get_command_output should only return the
    output string, not actually write to stderr."""

    utils.get_command_output(["git", "rev-pars", "HEAD"])

    out, err = capfd.readouterr()
    assert out == ""
    assert err == ""
