# Security

## Reporting

Open a private security advisory on GitHub, or email the maintainer listed in `pyproject.toml`.
Please do not open a public issue for anything exploitable.

## What this project handles

- **API keys** — read from the environment or a git-ignored `.env`, never written to a config,
  the ledger, the database, a run artefact or a log line. `alphalab doctor` reports a key as set
  or not set and never echoes it. A `detect-private-key` pre-commit hook guards commits.
- **Expression evaluation** — factor formulas are strings that Qlib evaluates. Everything passes
  through an AST whitelist (`src/alphalab/expr.py`) that rejects attribute access, imports,
  dunders and non-whitelisted operators *before* evaluation. This is the most
  security-sensitive code in the repo; changes to it need tests.
- **The dashboard** — read-only, binds to `127.0.0.1` by default, has no authentication and is
  not written to face a network. Artefact reads are whitelisted by name and validated against a
  path pattern, so a request cannot escape the work directory. If you expose it beyond
  localhost, put authentication in front of it — that is your responsibility, not the default.
- **Containers** — the image runs as a non-root user (uid 10001). `.dockerignore` keeps `.env`,
  `runs/` and `data/` out of the build context.

## What it deliberately does not do

It does not connect to a broker, hold credentials for one, or place orders. There is no
execution path to attack.
