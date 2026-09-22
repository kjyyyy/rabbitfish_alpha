"""Thin, provider-agnostic LLM harness.

- Providers: Anthropic (Claude), any OpenAI-compatible endpoint (OpenAI, local
  Ollama at http://localhost:11434/v1, LiteLLM proxy...), and a deterministic
  `mock` for tests/CI.
- Every call is appended to runs/<name>/llm_calls.jsonl (prompt hash, model,
  tokens, latency) and cached in SQLite by prompt hash, so re-running a batch
  is free and byte-for-byte reproducible - reproducibility comes from the
  cache, not from temperature (some newer models reject the parameter).
- Output is parsed as JSON and validated against a Pydantic schema; one
  automatic repair retry on invalid output.
API keys come from the environment (.env), never from config files."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Callable, Optional, Type

from pydantic import BaseModel, ValidationError


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    """The run hit its own token or call ceiling. Raised, never silently ignored:
    an agent loop with no ceiling is an unbounded bill and an unbounded trial
    count, and the trial count is the denominator of every Deflated Sharpe here."""


# Env overrides beat config, because a container cannot edit the YAML it ships
# with: compose points the lab at `http://ollama:11434/v1` while the same file
# says `localhost` for laptop use.
ENV_BASE_URL = "ALPHALAB_LLM_BASE_URL"
ENV_CRITIC_BASE_URL = "ALPHALAB_CRITIC_BASE_URL"

_RETRYABLE = ("timeout", "connection", "rate", "429", "500", "502", "503", "504",
              "overloaded", "unavailable", "reset")


def _is_retryable(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    if status is not None and 400 <= status < 500:
        return False                                   # auth, bad request: retrying cannot help
    blob = f"{type(e).__name__} {e}".lower()
    return any(w in blob for w in _RETRYABLE)


def _extract_json(text: str):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError("no JSON found in model output")
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start:end + 1])


class LLMClient:
    def __init__(self, provider: str, model: str, run_dir: Path, base_url: Optional[str] = None,
                 max_tokens: int = 4000, mock_fn: Optional[Callable[[str, str], str]] = None,
                 timeout_s: float = 120.0, max_retries: int = 3,
                 max_calls: int = 0, max_run_tokens: int = 0, role: str = "proposer"):
        env_key = ENV_CRITIC_BASE_URL if role == "critic" else ENV_BASE_URL
        self.provider, self.model = provider, model
        self.base_url = os.environ.get(env_key) or base_url
        self.max_tokens = max_tokens
        self.timeout_s, self.max_retries = timeout_s, max(0, int(max_retries))
        self.max_calls, self.max_run_tokens = max_calls, max_run_tokens
        self.calls = 0
        self.tokens = 0
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "llm_calls.jsonl"
        self.db = sqlite3.connect(self.run_dir / "llm_cache.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)")
        self.mock_fn = mock_fn
        self._client = None

    # ---- raw completion ------------------------------------------------------
    def _raw(self, system: str, user: str) -> tuple[str, dict]:
        if self.provider == "mock":
            if not self.mock_fn:
                raise LLMError("mock provider needs mock_fn")
            return self.mock_fn(system, user), {"input_tokens": 0, "output_tokens": 0}
        if self.provider == "anthropic":
            if self._client is None:
                try:
                    import anthropic
                except ImportError:
                    raise LLMError("the `anthropic` package is not installed: "
                                   "pip install -e '.[llm]'") from None
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    raise LLMError("ANTHROPIC_API_KEY not set (see .env.example)")
                self._client = anthropic.Anthropic(timeout=self.timeout_s, max_retries=0)
            r = self._client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                             system=system,
                                             messages=[{"role": "user", "content": user}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            return text, {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}
        if self.provider == "openai":
            if self._client is None:
                try:
                    from openai import OpenAI
                except ImportError:
                    raise LLMError("the `openai` package is not installed (it drives Ollama and "
                                   "vLLM too): pip install -e '.[llm]'") from None
                self._client = OpenAI(base_url=self.base_url, timeout=self.timeout_s,
                                      max_retries=0,
                                      api_key=os.environ.get("OPENAI_API_KEY", "ollama"))
            r = self._client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            u = getattr(r, "usage", None)
            return r.choices[0].message.content, {
                "input_tokens": getattr(u, "prompt_tokens", 0), "output_tokens": getattr(u, "completion_tokens", 0)}
        raise LLMError(f"unknown provider {self.provider}")

    def _raw_with_retry(self, system: str, user: str) -> tuple[str, dict]:
        """Bounded exponential backoff. A wedged local model server used to hang
        a discovery run forever; now it fails in `timeout_s` and retries a few
        times before giving up with a message that names the endpoint."""
        delay, last, tried = 1.0, None, 0
        for attempt in range(self.max_retries + 1):
            tried = attempt + 1
            try:
                return self._raw(system, user)
            except LLMError:
                raise                                  # missing key or package: not transient
            except Exception as e:                     # noqa: BLE001 - provider SDKs raise their own
                last = e
                if attempt >= self.max_retries or not _is_retryable(e):
                    break
                time.sleep(delay)
                delay = min(delay * 2, 20.0)
        where = self.base_url or f"{self.provider} default endpoint"
        raise LLMError(f"{type(last).__name__} from {where} after {tried} "
                       f"attempt{'s' if tried > 1 else ''}: {str(last)[:200]}") from None

    def _check_budget(self):
        if self.max_calls and self.calls >= self.max_calls:
            raise BudgetExceeded(f"call budget spent: {self.calls}/{self.max_calls} "
                                 f"(llm.max_calls_per_run)")
        if self.max_run_tokens and self.tokens >= self.max_run_tokens:
            raise BudgetExceeded(f"token budget spent: {self.tokens}/{self.max_run_tokens} "
                                 f"(llm.max_tokens_per_run)")

    def complete(self, system: str, user: str, tag: str = "") -> tuple[str, str]:
        """Returns (text, prompt_sha). Cached by (provider, model, system, user)."""
        key = hashlib.sha256(json.dumps([self.provider, self.model, system, user]).encode()).hexdigest()
        row = self.db.execute("SELECT v FROM cache WHERE k=?", (key,)).fetchone()
        cached = row is not None
        t0 = time.time()
        if cached:
            text, usage = row[0], {"input_tokens": 0, "output_tokens": 0}
        else:
            self._check_budget()                       # cached calls are free and never counted
            text, usage = self._raw_with_retry(system, user)
            self.calls += 1
            self.tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, text))
            self.db.commit()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                    tag=tag, provider=self.provider, model=self.model,
                                    prompt_sha=key[:16], cached=cached,
                                    latency_s=round(time.time() - t0, 2), **usage)) + "\n")
        return text, key[:16]

    def structured(self, system: str, user: str, schema: Type[BaseModel], tag: str = "",
                   many: bool = False):
        """Parse JSON output into `schema` (or a list of it). One repair retry."""
        text, sha = self.complete(system, user, tag)
        for attempt in range(2):
            try:
                obj = _extract_json(text)
                if many:
                    obj = obj if isinstance(obj, list) else obj.get("items", [])
                    return [schema(**o) for o in obj], sha
                return schema(**obj), sha
            except (LLMError, ValidationError, json.JSONDecodeError, TypeError) as e:
                if attempt:
                    raise LLMError(f"invalid structured output: {e}") from None
                text, sha = self.complete(system, user + f"\n\nYour previous answer was invalid "
                                          f"({str(e)[:200]}). Return ONLY valid JSON.", tag + ":repair")
