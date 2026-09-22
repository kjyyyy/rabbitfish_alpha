"""`alphalab init` - from a fresh clone to a runnable lab in one command.

Writes a `.env` (git-ignored) and a starter config for the chosen model stack,
then prints the three commands that follow. It never overwrites an existing
file and never asks for a key: keys go in `.env`, which the loader reads at
start-up, so nothing secret ever reaches a config file, the ledger or a commit.
"""
from __future__ import annotations

import shutil
from pathlib import Path

STACKS = {
    "mock":      ("configs/local_offline.yaml", "no network, no key, deterministic - start here"),
    "ollama":    ("configs/local_ollama.yaml",  "local models: ollama serve && ollama pull llama3.1:8b"),
    "vllm":      ("configs/local_vllm.yaml",    "local GPU serving on :8000"),
    "anthropic": ("configs/cn_csi300.yaml",     "Claude proposes, a local model critiques"),
}

ENV_TEMPLATE = """# alphalab environment - git-ignored, never commit this file
# Anthropic (only if llm.provider or llm.critic_provider is "anthropic")
ANTHROPIC_API_KEY={anthropic}
# Any OpenAI-compatible endpoint. For Ollama or vLLM any non-empty value works.
OPENAI_API_KEY={openai}

# Point the agents at a different endpoint without editing the config.
# Env beats config, which is how the same YAML works on a laptop and in Docker.
# ALPHALAB_LLM_BASE_URL=http://localhost:11434/v1
# ALPHALAB_CRITIC_BASE_URL=http://localhost:11434/v1

# Storage: unset means SQLite at runs/alphalab.db
# DATABASE_URL=postgresql+psycopg://alphalab:alphalab@localhost:5432/alphalab
"""


def run(stack: str = "mock", force: bool = False, log=print) -> dict:
    if stack not in STACKS:
        raise SystemExit(f"unknown stack '{stack}' - choose one of: {', '.join(STACKS)}")
    config, note = STACKS[stack]
    created, kept = [], []

    env = Path(".env")
    if env.exists() and not force:
        kept.append(".env")
    else:
        env.write_text(ENV_TEMPLATE.format(
            anthropic="", openai="ollama" if stack in ("ollama", "vllm") else ""))
        created.append(".env")

    if not Path(config).exists():                     # a clone always has these; a copy might not
        src = Path("configs/cn_csi300.yaml")
        if src.exists():
            shutil.copy(src, config)
            created.append(config)

    log(f"stack: {stack} - {note}")
    for f in created:
        log(f"  created {f}")
    for f in kept:
        log(f"  kept    {f} (already present; --force to replace)")
    if stack == "anthropic":
        log("\n  put ANTHROPIC_API_KEY=sk-ant-... in .env  (it is git-ignored)")
    log(f"""
next:
  make db                            # create/upgrade the research database
  alphalab doctor -c {config}   # check data, keys, database, model endpoints
  alphalab download-cn               # free CSI-300 data (~570MB), or:
  alphalab ingest --csv <dir>        # use your own OHLCV CSVs instead
  alphalab sanity -c {config}
""")
    return dict(stack=stack, config=config, created=created, kept=kept)
