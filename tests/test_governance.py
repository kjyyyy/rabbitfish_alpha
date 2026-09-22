"""Assumption register, exception log, and the fundamentals-timing measurement."""
import json

import pytest

from alphalab.audit import fundamentals_timing_bias
from alphalab.config import Config
from alphalab.governance import assumption_register, exceptions, log_exception, write_register


def test_register_records_the_choices_that_change_results(tmp_path):
    cfg = Config(workdir=str(tmp_path))
    reg = assumption_register(cfg)
    assert "close of day t+1" in reg["execution"]["trade_time"]
    assert reg["statistics"]["trial_counting"].startswith("every candidate")
    assert reg["data"]["pit_rule"].startswith("fundamentals are joined on filing date")
    p = write_register(cfg)
    assert json.loads(p.read_text())["config_name"] == cfg.name


def test_exception_log_is_append_only(tmp_path):
    cfg = Config(workdir=str(tmp_path))
    log_exception(cfg, "exclusion", "2020-02..2020-04", "COVID gap in the CN calendar")
    log_exception(cfg, "filter", "microcaps", "excluded below 100m ADV")
    rows = exceptions(cfg)
    assert len(rows) == 2 and rows[0]["kind"] == "exclusion"


@pytest.mark.parametrize("lag", [30, 45, 90])
def test_period_end_join_inflates_ic_and_worsens_with_lag(lag):
    r = fundamentals_timing_bias(lag_days=lag)
    assert r["inflation"] > 0                       # the leak always flatters here
    assert r["ic_period_end_join"] > r["ic_filing_date_join"]


def test_timing_bias_grows_with_reporting_lag():
    short = fundamentals_timing_bias(lag_days=30)["inflation"]
    long = fundamentals_timing_bias(lag_days=90)["inflation"]
    assert long > short * 1.5
