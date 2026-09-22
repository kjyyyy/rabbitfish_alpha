"""Configuration: one YAML file per market/experiment (see configs/).
Everything that could be tuned is set here BEFORE looking at results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field


class Costs(BaseModel):
    commission: float = 0.0003        # one-way, fraction of traded value
    slippage: float = 0.0010          # one-way spread + impact estimate
    stamp_buy: float = 0.0            # UK: 0.005 on share purchases
    stamp_sell: float = 0.0           # CN: 0.0005 since 2023-08-28
    stamp_sell_before: Optional[float] = None
    stamp_change_date: Optional[str] = None


class Market(BaseModel):
    name: Literal["cn", "us", "uk", "crypto", "futures"] = "cn"
    # What KIND of market this is, which decides more than the venue does:
    #   equity  - a wide cross-section, business-day calendar, no carry
    #   crypto  - 24/7, perpetual funding as a cash flow, brutal survivorship
    #   futures - dated contracts, a roll, tick-denominated costs, margin
    # `asset_class` drives the calendar, the cost model and the structural
    # sanity ceiling; `name` remains the venue/region for Qlib.
    asset_class: Literal["equity", "crypto", "futures"] = "equity"
    sessions_per_year: int = 252        # 365 for crypto: there are no weekends
    rebalances_per_year: int = 52
    qlib_region: str = "cn"
    provider_uri: str = "data/cn_data"
    universe: str = "csi300"
    benchmark: str = "SH000300"
    point_in_time_universe: bool = True
    survivorship_note: str = ""
    price_limits: bool = True          # CN +/-10% (20% ChiNext/STAR)
    # traded value per day, in currency. CN qlib data: $amount is in thousands
    # of yuan and $volume is in lots of 100 shares, so both need scaling.
    adv_expr: str = "$amount"
    adv_scale: float = 1000.0
    costs: Costs = Field(default_factory=Costs)

    # --- futures and perpetuals ------------------------------------------
    # A roll is a round trip paid every cycle whether or not the signal moved,
    # so it is configured here rather than inferred from turnover.
    roll_method: Literal["calendar", "open_interest", "volume"] = "calendar"
    roll_offset_days: int = 5
    roll_lag_days: int = 1              # liquidity rules must decide on past data
    adjust: Literal["ratio", "back", "none"] = "ratio"
    rolls_per_year: int = 4
    # Perpetual funding: a holding cash flow, not a transaction cost. Positive
    # means longs pay shorts.
    funding_interval_hours: int = 8
    funding_is_signal: bool = False     # harvesting funding is a strategy, not a cost line


class Splits(BaseModel):
    data_start: str = "2010-01-01"
    discover_start: str = "2012-01-01"
    discover_end: str = "2020-12-31"
    valid_years: list[int] = [2021, 2022, 2023, 2024]
    holdout_years: list[int] = [2025, 2026]
    holdout_burned: bool = False       # set True once results have been seen
    data_end: str = "2026-09-18"
    # The last N years of the DISCOVERY window are held back from the search
    # allocator, so the bandit can be rewarded on evidence it did not fit.
    # This is deliberately inside discovery: rewarding on `valid_years` would
    # spend the validation window on search and leave nothing clean to validate.
    inner_holdout_years: int = 2

    @property
    def inner_end(self) -> str:
        """Last date the search allocator is allowed to learn from."""
        return f"{int(self.discover_end[:4]) - self.inner_holdout_years}{self.discover_end[4:]}"


class Gates(BaseModel):
    t_stat_min: float = 3.0            # Harvey-Liu-Zhu
    dsr_min: float = 0.95              # Deflated Sharpe probability
    max_corr_to_accepted: float = 0.7
    max_nodes: int = 25                # complexity caps (AlphaAgent-style)
    max_raw_fields: int = 4
    max_constants: int = 6
    max_zoo_overlap: int = 8           # largest common subtree vs zoo (AlphaAgent default 8)
    probation_t_min: float = 3.0       # library entry (probation) before full DSR pass
    bandit_reward_t_min: float = 1.0   # inner-holdout |t| a family must clear to be rewarded
    promote_t_min: float = 2.0         # probation -> active: two consecutive rechecks at this t
    max_per_family: int = 4            # diversity cap per mechanism family (Hubble-style)


class Mining(BaseModel):
    n_random: int = 120
    gp_generations: int = 3
    gp_population: int = 40
    gp_lambda_nodes: float = 0.05      # fitness = t(IC) - lambda*nodes - mu*max|corr|
    gp_mu_corr: float = 2.0
    seed: int = 7
    # Every trial raises the Deflated-Sharpe bar for every future candidate,
    # whether or not anything was learned. 0 = no budget (the bar just keeps
    # rising); set it to make the trade-off explicit.
    trial_budget: int = 0


class Trading(BaseModel):
    horizon: int = 5
    label_expr: str = "Ref($close, -6) / Ref($close, -1) - 1"
    topk: int = 30
    keep_rank: int = 60


class Model(BaseModel):
    train_years: int = 6
    purge_days: int = 10
    combiner_lookback_days: int = 250  # dynamic IC weighting window
    combiner_shrink: float = 0.5       # shrink weights toward equal
    lgbm_rounds: int = 1000
    lgbm_early_stop: int = 50
    lgbm_params: dict = Field(default_factory=lambda: dict(
        objective="regression", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
        feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0,
        num_threads=2, verbose=-1, seed=7))


class LLM(BaseModel):
    provider: Literal["anthropic", "openai", "mock"] = "anthropic"
    model: str = "claude-sonnet-5"
    critic_provider: Literal["anthropic", "openai", "mock"] = "openai"
    critic_model: str = "llama3.1:8b"   # a different family, e.g. local Ollama
    base_url: Optional[str] = None      # e.g. http://localhost:11434/v1 for Ollama
    critic_base_url: Optional[str] = "http://localhost:11434/v1"
    training_cutoff: Optional[str] = None  # model knowledge cutoff, for leakage flags
    max_tokens: int = 4000
    timeout_s: float = 120.0           # a wedged local server must not hang a run
    max_retries: int = 3               # bounded backoff on transient failures
    max_calls_per_run: int = 200       # 0 = unlimited; agent loops need a ceiling
    max_tokens_per_run: int = 2_000_000


class Storage(BaseModel):
    """CSV stays the human-readable mirror; the database is the queryable record.
    `database_url` is usually left empty and taken from the DATABASE_URL env var
    (sqlite by default, Postgres in production)."""
    use_database: bool = True
    database_url: Optional[str] = None
    csv_mirror: bool = True


class Config(BaseModel):
    name: str = "cn_csi300"
    market: Market = Field(default_factory=Market)
    splits: Splits = Field(default_factory=Splits)
    gates: Gates = Field(default_factory=Gates)
    mining: Mining = Field(default_factory=Mining)
    trading: Trading = Field(default_factory=Trading)
    model: Model = Field(default_factory=Model)
    llm: LLM = Field(default_factory=LLM)
    storage: Storage = Field(default_factory=Storage)
    workdir: str = "runs"

    # ---- paths ------------------------------------------------------------
    @property
    def run_dir(self) -> Path:
        p = Path(self.workdir) / self.name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_dir(self) -> Path:
        p = Path(self.workdir) / ".cache"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def sha(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:12]


def load(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return Config(**data)
