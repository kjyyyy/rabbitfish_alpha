"""CLI argument handling.

The shared parent-parser idiom silently broke `-c` BEFORE the subcommand: the
subparser wrote its own default over the value, so the command ran against the
wrong config while looking perfectly correct. Regression-tested here because it
was claimed to work for three versions before anyone checked.
"""
import argparse

import pytest

from alphalab import cli


@pytest.mark.parametrize("argv", [
    ["-c", "configs/local_offline.yaml", "journal"],        # before the subcommand
    ["journal", "-c", "configs/local_offline.yaml"],        # after it
])
def test_config_flag_works_on_either_side_of_the_subcommand(argv, monkeypatch, tmp_path):
    seen = {}

    def fake_load(path):
        seen["path"] = str(path)
        raise SystemExit(0)

    monkeypatch.setattr(cli, "load", fake_load)
    monkeypatch.chdir(_repo_root())
    with pytest.raises(SystemExit):
        cli.main(argv)
    assert seen["path"] == "configs/local_offline.yaml"


def test_log_format_flag_works_on_either_side(monkeypatch):
    chosen = []
    monkeypatch.setattr(cli, "load", lambda p: (_ for _ in ()).throw(SystemExit(0)))
    import alphalab.logging_setup as L
    monkeypatch.setattr(L, "configure", lambda fmt=None, level="INFO": chosen.append(fmt))
    monkeypatch.chdir(_repo_root())
    for argv in (["--log-format", "json", "journal"], ["journal", "--log-format", "json"]):
        with pytest.raises(SystemExit):
            cli.main(argv)
    assert chosen == ["json", "json"]


def test_a_missing_config_is_a_message_not_a_traceback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["journal", "-c", "nope.yaml"])
    assert "no config at nope.yaml" in str(e.value)
    assert "alphalab init" in str(e.value)


def test_suppress_default_is_what_makes_this_work():
    """Guard the mechanism itself: an ordinary default reintroduces the bug."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default=None)
    ap = argparse.ArgumentParser(parents=[common])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("go", parents=[common])
    assert ap.parse_args(["-c", "x", "go"]).config is None, "the bug, reproduced"

    common2 = argparse.ArgumentParser(add_help=False)
    common2.add_argument("-c", "--config", default=argparse.SUPPRESS)
    ap2 = argparse.ArgumentParser(parents=[common2])
    sub2 = ap2.add_subparsers(dest="cmd")
    sub2.add_parser("go", parents=[common2])
    assert ap2.parse_args(["-c", "x", "go"]).config == "x", "the fix"


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
