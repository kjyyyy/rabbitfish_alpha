import json
import os
from unittest import mock

import pytest

from alphalab.agents import roles
from alphalab.agents.harness import LLMClient
from alphalab.config import Config
from alphalab.ledger import Ledger


def _cfg(tmp_path):
    c = Config(workdir=str(tmp_path))
    c.llm.provider = "mock"
    c.llm.critic_provider = "mock"
    return c


def test_harness_caches_and_logs(tmp_path):
    calls = []

    def fn(s, u):
        calls.append(u)
        return '{"consistent": true, "reason": "ok"}'
    c = LLMClient("mock", "m", tmp_path, mock_fn=fn)
    a, sha1 = c.complete("sys", "hello")
    b, sha2 = c.complete("sys", "hello")
    assert a == b and sha1 == sha2 and len(calls) == 1          # second call served from cache
    lines = (tmp_path / "llm_calls.jsonl").read_text().splitlines()
    assert json.loads(lines[1])["cached"] is True


def test_proposer_audits_and_logs_every_reject(tmp_path):
    cfg = _cfg(tmp_path)
    kept = roles.propose(cfg, n=4, log=lambda *_: None)
    names = {k["name"] for k in kept}
    assert "llm_lookahead_attempt" not in names and len(kept) == 3
    rejects = [r for r in Ledger(cfg.run_dir / "ledger.csv").rows() if r["status"] == "rejected"]
    assert any("look-ahead" in r["reason"] for r in rejects)
    roles.critique(cfg, log=lambda *_: None)
    rows = [json.loads(x) for x in (cfg.run_dir / "llm_candidates.jsonl").read_text().splitlines()]
    assert all(r.get("critic") for r in rows if r["status"] == "ok")


# --------------------------------------------------------------------------
# harness robustness: a wedged or flaky endpoint must not hang or kill a run
# --------------------------------------------------------------------------
def _client(tmp_path, **kw):
    from alphalab.agents.harness import LLMClient
    return LLMClient("mock", "m", tmp_path, mock_fn=lambda s, u: '{"ok": true}', **kw)


def test_transient_failures_are_retried_then_succeed(tmp_path):
    calls = {"n": 0}

    def flaky(system, user):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("connection reset by peer")
        return '{"ok": true}'

    c = _client(tmp_path, max_retries=3)
    c.mock_fn = flaky
    with mock.patch("time.sleep"):                 # no real backoff in tests
        text, _ = c.complete("s", "u")
    assert calls["n"] == 3 and "ok" in text


def test_retries_are_bounded_and_name_the_endpoint(tmp_path):
    from alphalab.agents.harness import LLMError

    def dead(system, user):
        raise TimeoutError("timed out")

    c = _client(tmp_path, max_retries=2, base_url="http://ollama:11434/v1")
    c.mock_fn = dead
    with mock.patch("time.sleep"), pytest.raises(LLMError) as e:
        c.complete("s", "u")
    assert "3 attempts" in str(e.value) and "ollama" in str(e.value)


def test_non_transient_failures_are_not_retried(tmp_path):
    from alphalab.agents.harness import LLMError
    calls = {"n": 0}

    def unauthorized(system, user):
        calls["n"] += 1
        err = RuntimeError("invalid api key")
        err.status_code = 401
        raise err

    c = _client(tmp_path, max_retries=3)
    c.mock_fn = unauthorized
    with mock.patch("time.sleep"), pytest.raises(LLMError):
        c.complete("s", "u")
    assert calls["n"] == 1, "a bad key is not worth retrying"


def test_budget_stops_a_runaway_loop_but_cached_calls_stay_free(tmp_path):
    from alphalab.agents.harness import BudgetExceeded

    c = _client(tmp_path, max_calls=2)
    c.complete("s", "one")
    c.complete("s", "two")
    for _ in range(5):
        c.complete("s", "one")                     # cached: never counted
    with pytest.raises(BudgetExceeded):
        c.complete("s", "three")


def test_env_overrides_the_configured_base_url(tmp_path, monkeypatch):
    """Compose points the lab at the ollama service while the YAML says localhost."""
    monkeypatch.setenv("ALPHALAB_LLM_BASE_URL", "http://ollama:11434/v1")
    assert _client(tmp_path, base_url="http://localhost:11434/v1").base_url == \
        "http://ollama:11434/v1"
    monkeypatch.setenv("ALPHALAB_CRITIC_BASE_URL", "http://vllm:8000/v1")
    assert _client(tmp_path, base_url="http://localhost:11434/v1", role="critic").base_url == \
        "http://vllm:8000/v1"


def test_dotenv_is_actually_loaded_and_the_real_environment_wins(tmp_path, monkeypatch):
    """.env.example told users to put keys here long before anything read it."""
    from alphalab.env import load as load_env

    f = tmp_path / ".env"
    f.write_text('# comment\nANTHROPIC_API_KEY=sk-test-123\nexport OPENAI_API_KEY="ollama"\n'
                 'ALPHALAB_LLM_BASE_URL=http://localhost:11434/v1\nJUNK\n')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ALPHALAB_LLM_BASE_URL", "http://ollama:11434/v1")

    loaded = load_env(f)
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test-123"
    assert os.environ["OPENAI_API_KEY"] == "ollama"          # quotes and `export` stripped
    assert os.environ["ALPHALAB_LLM_BASE_URL"] == "http://ollama:11434/v1", \
        "an exported variable must beat the file, or -e on docker run would do nothing"
    assert set(loaded.values()) == {"set"}, "the loader must never return secret values"
