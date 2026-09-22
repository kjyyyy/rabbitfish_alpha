"""Structured logging: an unattended run must be readable after the fact."""
import json
import logging

from alphalab import logging_setup as L


def _capture(caplog, fmt):
    L.configure(fmt)
    return logging.getLogger(L.LOGGER)


def test_json_lines_parse_and_carry_run_context(capsys):
    L.configure("json")
    L.bind(config="cn_csi300", version="0.12.0")
    L.get("stage").info("hello", extra={"stage": "discover", "done": 3})
    err = capsys.readouterr().err.strip().splitlines()
    rec = json.loads(err[-1])
    assert rec["msg"] == "hello" and rec["level"] == "info"
    assert rec["config"] == "cn_csi300" and rec["version"] == "0.12.0"
    assert rec["stage"] == "discover" and rec["done"] == 3
    assert rec["ts"].endswith("Z")


def test_progress_emits_a_heartbeat_with_rate_and_eta(capsys):
    L.configure("json")
    with L.progress("evaluate", total=4, every=2) as p:
        for _ in range(4):
            p.tick()
    lines = [json.loads(x) for x in capsys.readouterr().err.strip().splitlines()]
    events = [x["event"] for x in lines]
    assert events[0] == "start" and events[-1] == "done"
    beats = [x for x in lines if x["event"] == "progress"]
    assert beats and beats[-1]["done"] == 4
    assert "elapsed_s" in beats[-1] and "rate_per_s" in beats[-1]


def test_a_failing_loop_is_logged_as_an_error_not_swallowed(capsys):
    L.configure("json")
    try:
        with L.progress("evaluate", total=2) as p:
            p.tick()
            raise ValueError("boom")
    except ValueError:
        pass
    last = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert last["event"] == "error" and last["level"] == "error" and "boom" in last["msg"]


def test_text_format_stays_human_readable(capsys):
    L.configure("text")
    L.get().info("plain line")
    assert "plain line" in capsys.readouterr().out
