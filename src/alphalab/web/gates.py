"""Every gate, stated as a rule with its live value and its consequence.

The dashboard shows a factor is "blocked by deflated sharpe" - which is
useless unless you can see what that rule actually is, what number it is
compared against, and where that number was set. This module answers those
three questions for each gate from the live config, so the page can never
drift from what the code enforces.

Gates are deliberately NOT editable from the dashboard. Not because editing is
hard, but because a slider that relaxes a threshold after you have seen which
candidates it rejects is the single most effective way to manufacture a false
discovery. Changing a gate is a config edit, and a config edit changes the
config hash, which marks every later run as a different experiment. That trail
is the point.
"""
from __future__ import annotations

from ..config import Config


def describe(cfg: Config) -> list[dict]:
    g, m, s, t = cfg.gates, cfg.mining, cfg.splits, cfg.trading
    return [
        dict(name="AST whitelist",
             rule="The formula must parse to a whitelisted expression tree: no attribute "
                  "access, no imports, no dunders, no unknown operators, no negative Ref "
                  "shifts.",
             value="always on", key="src/alphalab/expr.py",
             rejects="Anything that could execute code or read the future through a shift. "
                     "Qlib evaluates these strings, so this is the security boundary as well "
                     "as the research one.",
             stage="screen"),
        dict(name="Complexity cap",
             rule=f"At most {g.max_nodes} AST nodes, {g.max_raw_fields} distinct raw fields "
                  f"and {g.max_constants} constants.",
             value=f"{g.max_nodes} nodes", key="gates.max_nodes",
             rejects="Formulas complex enough to memorise the sample. Complexity buys "
                     "in-sample fit almost for free.",
             stage="screen"),
        dict(name="Originality",
             rule=f"Largest common subtree with the Alpha158 zoo and the existing library must "
                  f"be at most {g.max_zoo_overlap} nodes.",
             value=f"{g.max_zoo_overlap} nodes", key="gates.max_zoo_overlap",
             rejects="Rediscoveries of published factors dressed as new ones. A known factor "
                     "is not a discovery, and counting it as one inflates the trial count "
                     "with work someone else already did.",
             stage="screen"),
        dict(name="Look-ahead (future-noise test)",
             rule="Scramble all data after a cut date; every value before it must be "
                  "bit-identical. Any change means the formula reads the future.",
             value="always on", key="src/alphalab/leakage.py",
             rejects="Centred windows, global normalisation, and any operator that peeks. "
                     "Truncation tests do not work here because Qlib computes over the whole "
                     "stored series and then slices.",
             stage="evaluate"),
        dict(name="Numerical validity",
             rule="Reject if more than 30% of values are invalid or extreme, if coverage is "
                  "below the floor, or if cross-sections are near-constant.",
             value="30% invalid", key="src/alphalab/leakage.py",
             rejects="Degenerate factors that score well because they are almost constant, "
                     "or that are dominated by a handful of outliers.",
             stage="evaluate"),
        dict(name="Sign consistency",
             rule="If a hypothesis states a direction, the measured IC must have that sign.",
             value="always on", key="factors/hypotheses.py",
             rejects="A factor that 'works' backwards from its stated mechanism. That is not "
                     "the hypothesis being confirmed; it is a different, unstated one.",
             stage="gate"),
        dict(name="t-statistic",
             rule=f"|t| of the IC series, sampled every {t.horizon} days, must be at least "
                  f"{g.t_stat_min}.",
             value=str(g.t_stat_min), key="gates.t_stat_min",
             rejects="Everything that would clear the usual t >= 2. Harvey, Liu & Zhu argue "
                     "3.0 is the right bar once you account for how much has been tried "
                     "across the whole literature.",
             stage="gate"),
        dict(name="Deflated Sharpe",
             rule=f"DSR must be at least {g.dsr_min}, computed against the cumulative count of "
                  f"distinct formulas ever evaluated for this config - including rejects.",
             value=str(g.dsr_min), key="gates.dsr_min",
             rejects="The luckiest survivor of a large search. This is the gate nothing in "
                     "this repo has ever cleared, and the bar rises with every trial.",
             stage="gate"),
        dict(name="Correlation to accepted",
             rule=f"Absolute correlation with any already-accepted candidate must be below "
                  f"{g.max_corr_to_accepted}.",
             value=str(g.max_corr_to_accepted), key="gates.max_corr_to_accepted",
             rejects="Near-duplicates that would make a library look diversified while "
                     "holding one bet many times.",
             stage="gate"),
        dict(name="Family quota",
             rule=f"At most {g.max_per_family} accepted factors per mechanism family.",
             value=str(g.max_per_family), key="gates.max_per_family",
             rejects="A library that is really one idea in eight costumes.",
             stage="gate"),
        dict(name="Search reward (inner holdout)",
             rule=f"A family is rewarded when a child reaches |t| >= {g.bandit_reward_t_min} on "
                  f"the purged inner holdout - the last {s.inner_holdout_years} years of the "
                  f"discovery window, withheld from the allocator.",
             value=str(g.bandit_reward_t_min), key="gates.bandit_reward_t_min",
             rejects="Nothing directly. It decides where search EFFORT goes. Before v0.10 it "
                     "rewarded in-sample significance, which pointed the search at whatever "
                     "overfit best.",
             stage="search"),
        dict(name="Promotion",
             rule=f"probation -> active needs two CONSECUTIVE rechecks at t >= "
                  f"{g.promote_t_min} on data the factor was not discovered on, each on a "
                  f"different window.",
             value=str(g.promote_t_min), key="gates.promote_t_min",
             rejects="One lucky window. Re-running the recheck on the same sessions is "
                     "refused, because that is one piece of evidence counted twice.",
             stage="library"),
        dict(name="Retirement",
             rule="Two consecutive rechecks below t = 1.0 retire a factor. Any strong recheck "
                  "resets the count.",
             value="t < 1.0 twice", key="library.revalidate()",
             rejects="Keeps a decayed factor from sitting in the library forever on the "
                     "strength of the day it was found.",
             stage="library"),
        dict(name="Forward evidence",
             rule="13 clean pre-registered weeks. A week is clean only if the manifest was "
                  "written before the close that resolves it.",
             value="13 weeks", key="forward.publish()",
             rejects="Every claim above 'research-aid'. Nothing here has produced a clean "
                     "week yet.",
             stage="claim"),
        dict(name="Trial budget",
             rule=("No budget set: the Deflated-Sharpe bar simply keeps rising."
                   if not m.trial_budget else
                   f"Warn loudly once {m.trial_budget} distinct trials have been spent."),
             value=str(m.trial_budget or "none"), key="mining.trial_budget",
             rejects="Nothing. It exists to make the treadmill visible: every trial raises "
                     "the bar for every future candidate, learned or not.",
             stage="search"),
    ]


def config_file_hint(cfg: Config) -> dict:
    return dict(
        name=cfg.name,
        sha=cfg.sha(),
        how="Gates are set in the YAML config, before a run. Edit the file, not this page.",
        why="Changing a threshold after seeing which candidates it rejects is how a false "
            "discovery is manufactured. A config edit changes the config hash, which marks "
            "every later run as a different experiment - that trail is the control.",
        exception="If you must deviate for a specific run, record it: "
                  "alphalab exception --kind <kind> --scope <what> --reason <why>. It is "
                  "append-only and shows on the validity card.")
