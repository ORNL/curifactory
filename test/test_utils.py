from curifactory import utils


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
