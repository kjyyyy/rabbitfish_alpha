# Running the agents on local models

The lab is provider-agnostic. Anthropic is one option; anything speaking the OpenAI API is
another, which covers both local servers.

| | Ollama | vLLM |
|---|---|---|
| Hardware | CPU is fine | NVIDIA GPU |
| Start | `make up` | `make up PROFILE=vllm` |
| Pull a model | `docker compose exec ollama ollama pull llama3.1:8b` | set in `docker-compose.yml` command |
| Base URL | `http://localhost:11434/v1` | `http://localhost:8000/v1` |
| Config | `configs/local_ollama.yaml` | `configs/local_vllm.yaml` |
| Verify | `alphalab llm-check -c configs/local_ollama.yaml` | `alphalab llm-check -c configs/local_vllm.yaml` |

## Why two different models

`llm.provider` runs the proposer; `llm.critic_provider` runs the consistency critic. The defaults
put them in **different model families** (llama proposes, qwen reviews). A critic drawn from the
same family as the proposer tends to agree with it, which defeats the point of having one.

## What local models change about the research

Nothing structurally: proposals face the identical AST audit, complexity caps, originality check,
leakage test and statistical gates, and every proposal — accepted or rejected — is written to the
ledger and counts toward the trial count.

Two practical differences worth knowing:

- **Smaller models propose worse factors and malformed JSON more often.** The harness retries
  once on invalid output and logs the reject; expect a lower pass rate through the auditor, not
  silently worse research.
- **Set `llm.training_cutoff` to the real cutoff of the model you serve.** The validity card uses
  it to decide whether LLM-derived factors can ever reach the "historical-backtest" tier: if the
  model's training data covers the discovery window, only forward-tested data is clean.

## No model at all

`configs/local_offline.yaml` uses `provider: mock`, a deterministic stub. `make offline` runs the
entire pipeline with it — useful for air-gapped work, CI, and for checking that a change to the
gates did not depend on an LLM being present.
