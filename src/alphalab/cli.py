"""Command line: `alphalab <command> -c configs/cn_csi300.yaml`."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .config import load

CN_DATA_URL = "https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz"


def main(argv=None):
    # -c and --log-format work before OR after the subcommand.
    #
    # `default=SUPPRESS` is load-bearing: `common` is a parent of BOTH the
    # top-level parser and every subparser, so with an ordinary default the
    # subparser writes its default over whatever was given before the
    # subcommand. That silently broke `alphalab -c x.yaml discover`, which this
    # repo has claimed to support since v0.8 - it parsed fine and used the
    # wrong config. With SUPPRESS the attribute is set only when the user
    # actually passes the flag, so whichever position they use wins.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-format", choices=["text", "json"],
                        default=argparse.SUPPRESS,
                        help="json for unattended runs (env: ALPHALAB_LOG_FORMAT)")
    common.add_argument("-c", "--config", default=argparse.SUPPRESS)
    ap = argparse.ArgumentParser(prog="alphalab", description=__doc__, parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser

    def add_parser(name, **kw):
        kw.setdefault("parents", [common])
        return _add(name, **kw)
    sub.add_parser = add_parser
    sub.add_parser("download-cn", help="download the Qlib community China A-share dataset (~570MB)")
    i = sub.add_parser("init", help="scaffold .env and pick a model stack (start here)")
    i.add_argument("--stack", default="mock", choices=["mock", "ollama", "vllm", "anthropic"])
    i.add_argument("--force", action="store_true", help="overwrite an existing .env")
    d = sub.add_parser("doctor", help="check data, keys, database and model endpoints")
    d.add_argument("--skip-models", action="store_true", help="do not ping the LLM endpoints")
    ing = sub.add_parser("ingest", help="use your own OHLCV CSVs instead of the CN download")
    ing.add_argument("--csv", required=True, help="a directory of per-symbol CSVs, or one long CSV")
    ing.add_argument("--dest", default="data/my_market")
    ing.add_argument("--universe", default="all")
    ing.add_argument("--date-col", default="date")
    ing.add_argument("--symbol-col", default=None, help="only for a single long CSV")
    ing.add_argument("--region", default="us", choices=["us", "cn", "uk"])
    ing.add_argument("--force", action="store_true", help="ingest despite data problems")
    ing.add_argument("--write-config", default=None, metavar="PATH",
                     help="also write a ready-to-run config for this data")
    sub.add_parser("sanity", help="engine sanity checks (oracle / random / stale)")
    p = sub.add_parser("propose", help="LLM research agent proposes factors")
    p.add_argument("-n", type=int, default=20)
    sub.add_parser("critique", help="LLM critic checks hypothesis<->formula consistency")
    d = sub.add_parser("discover", help="stage 1: screen, evaluate, GP-refine, gate")
    d.add_argument("--no-gp", action="store_true")
    sub.add_parser("model", help="stage 2: walk-forward variants, holdout, validity cards")
    f = sub.add_parser("forward", help="forward pre-registration")
    f.add_argument("action", choices=["publish", "evaluate"])
    t = sub.add_parser("portfolio-trial", help="compare portfolio-construction layers + capacity curve")
    t.add_argument("--capital", type=float, default=1e6)
    sub.add_parser("audit", help="decision-time protocol audit: how much 'alpha' is convention?")
    sub.add_parser("register", help="write the assumption register for this config")
    sub.add_parser("llm-check", help="verify the LLM endpoints (Ollama / vLLM / Anthropic) work")
    db = sub.add_parser("db", help="database: upgrade | status | import-csv")
    db.add_argument("action", choices=["upgrade", "status", "import-csv", "verify", "sync-library"])
    ex = sub.add_parser("exception", help="log a deviation from the standard protocol")
    ex.add_argument("--kind", required=True, help="e.g. filter, exclusion, special-handling")
    ex.add_argument("--scope", required=True, help="what it applies to")
    ex.add_argument("--reason", required=True)
    ex.add_argument("--author", default="")
    sub.add_parser("validate", help="CPCV, overfitting factor, log-wealth, decay and cost sweep")
    sub.add_parser("revalidate", help="recheck the library on data it was not discovered on "
                                      "(promote, retire)")
    rp = sub.add_parser("repair", help="reconcile ledger schema, library duplicates, and stale "
                                       "revalidation artefacts")
    rp.add_argument("--apply", action="store_true", help="write fixes (default is dry-run)")
    sub.add_parser("hierarchy", help="family-level testing first, then within-family (cuts effective N)")
    sv = sub.add_parser("serve", help="read-only dashboard + JSON API on localhost")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("journal", help="summarise the ledger and library")
    cl = sub.add_parser("clean", help="prune caches (the evaluation and LLM caches grow forever)")
    cl.add_argument("--older-than", type=int, default=30, help="days; 0 removes everything")
    cl.add_argument("--dry-run", action="store_true")
    cy = sub.add_parser("cycle", help="one closed research cycle: propose -> critique -> discover "
                                      "-> model -> memory -> journal")
    cy.add_argument("-n", type=int, default=15, help="LLM proposals this cycle (0 = skip the LLM arm)")
    cy.add_argument("--no-gp", action="store_true")
    sub.add_parser("all", help="sanity -> discover -> model -> journal")
    a = ap.parse_args(argv)

    from .env import load as load_env
    from .logging_setup import bind, configure
    load_env()                       # keys from .env; anything already exported wins
    configure(getattr(a, "log_format", None))

    # `init` runs BEFORE a config exists - that is its whole purpose - so it is
    # dispatched before the config is loaded.
    if a.cmd == "init":
        from . import init_lab
        init_lab.run(a.stack, a.force)
        return

    path = Path(getattr(a, "config", None) or "configs/cn_csi300.yaml")
    if not path.exists():
        shipped = sorted(q.name for q in Path("configs").glob("*.yaml")) \
            if Path("configs").is_dir() else []
        sys.exit(f"no config at {path}\nrun `alphalab init` first, or pass -c <file>"
                 + (f" (shipped here: {', '.join(shipped)})" if shipped else ""))
    cfg = load(path)
    from .provenance import git_sha, version
    bind(config=cfg.name, config_sha=cfg.sha(), version=version(), git_sha=git_sha(short=True),
         cmd=a.cmd)

    if a.cmd == "download-cn":
        dest = Path(cfg.market.provider_uri)
        dest.mkdir(parents=True, exist_ok=True)
        tgz = dest.parent / "qlib_bin.tar.gz"
        subprocess.check_call(["curl", "-L", "-o", str(tgz), CN_DATA_URL])
        subprocess.check_call(["tar", "-xzf", str(tgz), "-C", str(dest), "--strip-components=1"])
        tgz.unlink()
        print(f"data ready in {dest}")
    elif a.cmd == "doctor":
        from . import doctor
        sys.exit(0 if doctor.run(cfg, check_models=not a.skip_models)["ok"] else 1)
    elif a.cmd == "ingest":
        from .sources import ingest
        ingest.run(a.csv, a.dest, a.universe, a.date_col, a.symbol_col, a.region, a.force,
                   a.write_config)
    elif a.cmd == "sanity":
        from . import sanity
        sys.exit(0 if sanity.run(cfg)["passed"] else 1)
    elif a.cmd == "propose":
        from .agents import roles
        roles.propose(cfg, a.n)
    elif a.cmd == "critique":
        from .agents import roles
        roles.critique(cfg)
    elif a.cmd == "discover":
        from .pipeline import discover
        discover.run(cfg, gp=not a.no_gp)
    elif a.cmd == "model":
        from .pipeline import model
        model.run(cfg)
    elif a.cmd == "forward":
        from . import forward
        forward.publish(cfg) if a.action == "publish" else forward.evaluate(cfg)
    elif a.cmd == "portfolio-trial":
        from .pipeline import portfolio_trial
        portfolio_trial.run(cfg, capital=a.capital)
    elif a.cmd == "audit":
        from . import audit
        audit.run(cfg)
    elif a.cmd == "llm-check":
        from . import llm_check
        res = llm_check.run(cfg)
        sys.exit(0 if all(v.get("ok") for v in res.values()) else 1)
    elif a.cmd == "db":
        from .db import maintenance
        getattr(maintenance, a.action.replace("-", "_"))(cfg)
    elif a.cmd == "register":
        from . import governance
        print(governance.write_register(cfg))
    elif a.cmd == "exception":
        from . import governance
        print(governance.log_exception(cfg, a.kind, a.scope, a.reason, a.author))
    elif a.cmd == "validate":
        from .pipeline import validate
        validate.run(cfg)
    elif a.cmd == "revalidate":
        from .pipeline import revalidate
        revalidate.run(cfg)
    elif a.cmd == "repair":
        from .pipeline import repair
        repair.run(cfg, apply=a.apply)
    elif a.cmd == "clean":
        from . import retention
        retention.run(cfg, older_than_days=a.older_than, dry_run=a.dry_run)
    elif a.cmd == "hierarchy":
        from .pipeline import hierarchy
        hierarchy.run(cfg)
    elif a.cmd == "serve":
        from .web.app import serve
        serve(cfg, a.host, a.port)
    elif a.cmd == "journal":
        from .agents import roles
        roles.journal(cfg)
    elif a.cmd == "cycle":
        import json as _json

        from . import memory
        from .agents import roles
        from .ledger import Ledger
        from .pipeline import discover, model
        if a.n:
            try:
                roles.propose(cfg, a.n)
                roles.critique(cfg)
            except SystemExit as e:
                print(f"LLM arm skipped: {e}")
        discover.run(cfg, gp=not a.no_gp)
        model.run(cfg)
        mem = memory.build(Ledger(cfg.run_dir / "ledger.csv"), cfg.run_dir / "memory.json")
        roles.journal(cfg)
        print("\nresearch memory now holds: " + _json.dumps(
            {k: v["count"] for k, v in mem["good"].items()}) + " surviving mechanisms by family")
    elif a.cmd == "all":
        from . import sanity
        from .agents import roles
        from .pipeline import discover, model
        if not sanity.run(cfg)["passed"]:
            sys.exit("sanity failed")
        discover.run(cfg)
        model.run(cfg)
        roles.journal(cfg)


if __name__ == "__main__":
    main()
