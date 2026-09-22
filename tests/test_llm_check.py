"""llm-check must pass offline with the mock provider and fail loudly otherwise."""
from alphalab import llm_check
from alphalab.config import Config


def test_mock_provider_passes_with_no_network(tmp_path):
    cfg = Config(workdir=str(tmp_path))
    cfg.llm.provider = cfg.llm.critic_provider = "mock"
    res = llm_check.run(cfg, log=lambda *_: None)
    assert all(v["ok"] for v in res.values())
    assert res["proposer"]["cached_latency_s"] <= res["proposer"]["latency_s"]


def test_unreachable_endpoint_is_reported_not_raised(tmp_path):
    cfg = Config(workdir=str(tmp_path))
    cfg.llm.provider = "openai"
    cfg.llm.base_url = "http://127.0.0.1:9/v1"          # nothing listens here
    cfg.llm.critic_provider = "mock"
    res = llm_check.run(cfg, log=lambda *_: None)
    assert res["proposer"]["ok"] is False and res["proposer"]["error"]
    assert res["critic"]["ok"] is True
