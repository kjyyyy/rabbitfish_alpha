"""`alphalab llm-check` - prove the local model stack works before a research run.

The lab is provider-agnostic: Anthropic, or any OpenAI-compatible endpoint. Both
Ollama (`http://localhost:11434/v1`) and vLLM (`http://localhost:8000/v1`) speak
that protocol, so a local, fully offline suite needs no code changes - only
config. This command pings the endpoint, runs one structured-output round trip,
and reports latency and cache behaviour, so a failure is diagnosed here rather
than halfway through a discovery run.
"""
from __future__ import annotations

import time

from pydantic import BaseModel

from .agents.harness import LLMClient, LLMError
from .agents.roles import mock_fn
from .config import Config


class Ping(BaseModel):
    ok: bool
    model_note: str = ""


PROMPT = ('Reply with only this JSON and nothing else: {"ok": true, "model_note": '
          '"<the model family you belong to, 3 words max>"}')


def check_one(cfg: Config, role: str, log=print) -> dict:
    llm = cfg.llm
    provider = llm.critic_provider if role == "critic" else llm.provider
    model = llm.critic_model if role == "critic" else llm.model
    base = llm.critic_base_url if role == "critic" else llm.base_url
    client = LLMClient(provider, model, cfg.run_dir, base, llm.max_tokens, mock_fn=mock_fn,
                       timeout_s=min(llm.timeout_s, 30.0), max_retries=1, role=role)
    out = dict(role=role, provider=provider, model=model,
               base_url=client.base_url or "(provider default)")
    t0 = time.time()
    try:
        ping, sha = client.structured("Return only JSON.", PROMPT, Ping, tag=f"llm-check:{role}")
        out.update(ok=bool(ping.ok), latency_s=round(time.time() - t0, 2), prompt_sha=sha,
                   note=ping.model_note)
        t1 = time.time()
        client.structured("Return only JSON.", PROMPT, Ping, tag=f"llm-check:{role}")
        out["cached_latency_s"] = round(time.time() - t1, 3)
    except LLMError as e:
        out.update(ok=False, error=str(e)[:200])
    except Exception as e:                            # noqa: BLE001 - connection errors etc.
        out.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}")
    log(f"  {role:8s} {provider}:{model} @ {out['base_url']} -> "
        + ("OK" if out.get("ok") else f"FAILED - {out.get('error', 'unknown')}")
        + (f" ({out['latency_s']}s, cached {out['cached_latency_s']}s)" if out.get("ok") else ""))
    return out


def run(cfg: Config, log=print) -> dict:
    log("checking the model stack this config will use:")
    res = {r: check_one(cfg, r, log) for r in ("proposer", "critic")}
    if not all(v.get("ok") for v in res.values()):
        log("\nhints:")
        log("  ollama:  ollama serve && ollama pull llama3.1:8b   (base_url http://localhost:11434/v1)")
        log("  vllm:    vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000  (base_url http://localhost:8000/v1)")
        log("  offline: set provider to 'mock' to run the whole suite with no model at all")
    return res
