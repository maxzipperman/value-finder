"""Six fixed historical discovery specifications; default mode reads no final-score columns.

No network, API, alert or live-ledger imports. See FORECAST_STYLE_SETUP.md and the JSON protocol.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, time, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "forecast_style_protocol.json"
FORECAST_COLUMNS = ["game_id", "season", "start_utc", "home_team", "away_team",
                    "mos1_mph", "mos2_mph", "mos1_runtime", "mos2_runtime"]
TEAM_COLUMNS = ["game_id", "season", "date", "team", "game_type", "pass_rate_sit"]


def load_protocol(path=PROTOCOL):
    cfg = json.loads(Path(path).read_text())
    assert cfg["latest_season"] == 2025, "2026 stays sealed"
    assert len(cfg["models"]) == cfg["specifications_added"] == 6
    assert len({m["id"] for m in cfg["models"]}) == 6
    assert cfg["project_count_at_setup"] == cfg["project_count_before"] + 6
    return cfg


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def data_digest(d):
    """Fingerprint only projected historical rows, never bytes from the sealed part of a file."""
    labels = json.dumps([(c, str(d[c].dtype)) for c in d.columns]).encode()
    values = pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()
    return hashlib.sha256(labels + values).hexdigest()


def read_historical(path, columns, cfg):
    """Project named columns and filter before the parquet reader returns any rows."""
    if "season" not in columns:
        raise ValueError("Every table must expose its season for the sealed-data guard")
    d = pd.read_parquet(path, columns=columns, filters=[("season", "<=", cfg["latest_season"])])
    if d.season.isna().any() or (d.season > 2025).any():
        raise ValueError("Reader delivered a missing or sealed season")
    return d


def decision_time(kick):
    day = pd.Timestamp(kick).tz_convert("America/New_York").date() - timedelta(days=1)
    return pd.Timestamp(datetime.combine(day, time(19, 30))).tz_localize("America/Los_Angeles").tz_convert("UTC")


def prepare_forecasts(d, cfg):
    d = d.copy()
    if d.game_id.duplicated().any():
        raise ValueError("Duplicate game ids in the forecast table")
    d["start_utc"] = pd.to_datetime(d.start_utc, utc=True, errors="coerce")
    for c in ["mos1_runtime", "mos2_runtime"]:
        d[c] = pd.to_datetime(d[c], utc=True, errors="coerce")
    d["decision_utc"] = [decision_time(k) if pd.notna(k) else pd.NaT for k in d.start_utc]
    d["wind1"] = pd.to_numeric(d.mos1_mph, errors="coerce")
    d["wind2"] = pd.to_numeric(d.mos2_mph, errors="coerce")
    lag = pd.Timedelta(hours=cfg["mos_publication_lag_hours"])
    lead_dates = [(pd.Timestamp(k).tz_convert("America/New_York").date() - timedelta(days=1))
                  if pd.notna(k) else None for k in d.start_utc]
    rules = [
        ("missing_kickoff", d.start_utc.isna()),
        ("missing_forecast_or_runtime", ~np.isfinite(d.wind1) | ~np.isfinite(d.wind2)
         | d.mos1_runtime.isna() | d.mos2_runtime.isna()),
        ("negative_wind", (d.wind1 < 0) | (d.wind2 < 0)),
        ("reversed_forecast_times", d.mos2_runtime >= d.mos1_runtime),
        ("forecast_runtime_on_wrong_lead_date", (d.mos1_runtime.dt.date != pd.Series(lead_dates, index=d.index))
         | (d.mos2_runtime.dt.date != pd.Series([x-timedelta(days=1) if x else None for x in lead_dates], index=d.index))),
        ("forecast_not_published_by_decision", (d.mos1_runtime + lag > d.decision_utc)
         | (d.mos2_runtime + lag > d.decision_utc)),
        ("decision_not_before_kickoff", d.decision_utc >= d.start_utc),
    ]
    reason = pd.Series("", index=d.index)
    for label, mask in rules:
        reason.loc[reason.eq("") & mask] = label
    rejected = d.loc[reason.ne(""), ["game_id", "season"]].assign(reason=reason[reason.ne("")])
    kept = d[reason.eq("")].copy()
    kept["revision"] = kept.wind1 - kept.wind2
    kept["game_day"] = kept.start_utc.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    assert len(kept) + len(rejected) == len(d)
    return kept, rejected


def attach_style(forecasts, history, cfg):
    """Both teams' prior-game rates, available at the forecast decision; no current-game stats."""
    history = history.copy()
    if history.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate team-game statistics")
    history["date"] = pd.to_datetime(history.date, utc=True, errors="coerce")
    history["available_utc"] = history.date.dt.normalize() + pd.Timedelta(hours=cfg["style_reporting_lag_hours"])
    history["pass_rate_sit"] = pd.to_numeric(history.pass_rate_sit, errors="coerce")
    valid = (history.game_type.eq("REG") & history.available_utc.notna()
             & history.pass_rate_sit.between(0, 1))
    histories = {k: v.sort_values(["date", "game_id"], kind="stable")
                 for k, v in history[valid].groupby(["season", "team"])}
    records = []
    for r in forecasts.itertuples():
        rec = {"game_id": r.game_id}
        for side, team in [("home", r.home_team), ("away", r.away_team)]:
            h = histories.get((r.season, team), history.iloc[:0])
            h = h[(h.available_utc <= r.decision_utc) & (h.game_id != r.game_id)]
            h = h.tail(cfg["style_prior_games"])
            enough = len(h) >= cfg["style_min_prior_games"]
            rec[f"{side}_prior_n"] = len(h)
            rec[f"{side}_style"] = float(h.pass_rate_sit.mean()) if enough else np.nan
            rec[f"{side}_prior_games"] = "|".join(h.game_id.astype(str))
            rec[f"{side}_latest_available_utc"] = h.available_utc.max() if len(h) else pd.NaT
        records.append(rec)
    extra = pd.DataFrame(records)
    if extra.empty:
        extra = pd.DataFrame(columns=["game_id"] + [f"{side}_{name}" for side in ["home", "away"]
                             for name in ["style", "prior_n", "prior_games", "latest_available_utc"]])
    d = forecasts.merge(extra, on="game_id", how="left", validate="one_to_one")
    d["style"] = (d.home_style + d.away_style) / 2
    d["wind_style"] = d.wind1 * d.style
    return d


def make_inputs(root, cfg):
    data, rejections, metadata = {}, {}, {}
    for sport in ["nfl", "cfb"]:
        p = Path(root) / f"{sport}-weather/data/processed/mos_replay.parquet"
        raw = read_historical(p, FORECAST_COLUMNS, cfg)
        d, reject = prepare_forecasts(raw, cfg)
        if sport == "nfl":
            tp = Path(root) / "nfl-weather/data/processed/team_games.parquet"
            history = read_historical(tp, TEAM_COLUMNS, cfg)
            d = attach_style(d, history, cfg)
            metadata["nfl_history_projected_sha256"] = data_digest(history)
        data[sport], rejections[sport] = d, reject
        metadata[sport] = {"input_rows": len(raw), "eligible_revision_rows": len(d),
                           "eligible_style_rows": int(d["style"].notna().sum()) if sport == "nfl" else None,
                           "seasons": sorted(int(s) for s in d.season.unique()),
                           "rejections": dict(Counter(reject.reason)), "projected_input_sha256": data_digest(raw)}
    return data, rejections, metadata


def attach_outcomes(d, root, sport, cfg):
    """Called only in explicit run mode; no 2026 row is returned, including score columns."""
    columns = ["game_id", "season", "total", "total_line" if sport == "nfl" else "close_total"]
    source = Path(root) / f"{sport}-weather/data/processed/mos_replay.parquet"
    outcomes = read_historical(source, columns, cfg)
    line = columns[-1]
    outcomes["target"] = pd.to_numeric(outcomes.total, errors="coerce") - pd.to_numeric(outcomes[line], errors="coerce")
    return d.merge(outcomes[["game_id", "season", "target"]], on=["game_id", "season"],
                   how="left", validate="one_to_one")


def fit_predict(train, test, features, penalty):
    x = train[features].to_numpy(float)
    xt = test[features].to_numpy(float)
    mean, sd = x.mean(axis=0), x.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    a = np.column_stack([np.ones(len(x)), (x - mean) / sd])
    b = np.column_stack([np.ones(len(xt)), (xt - mean) / sd])
    regularizer = np.diag([0.0] + [penalty] * len(features))
    coef = np.linalg.solve(a.T @ a + regularizer, a.T @ train.target.to_numpy(float))
    return b @ coef, {"mean": mean.tolist(), "sd": sd.tolist(), "coef": coef.tolist()}


def walk_forward(d, specs, cfg):
    """An expanding training window; paired models always see identical train/test games."""
    if d.season.isna().any() or (d.season > 2025).any():
        raise ValueError("Sealed season passed to the evaluator")
    d = d.sort_values(["season", "game_id"], kind="stable")
    features = sorted({f for m in specs for f in m["features"]})
    required = features + ["target"]
    finite = np.isfinite(d[required].to_numpy(float)).all(axis=1)
    excluded = d.loc[~finite, ["game_id", "season"]].assign(reason="missing_target_or_required_feature")
    d = d[finite].copy()
    rows, folds, coefficients = [], [], []
    for season in sorted(d.season.unique()):
        train, test = d[d.season < season], d[d.season == season]
        nseasons = train.season.nunique()
        eligible = (nseasons >= cfg["minimum_prior_seasons"] and len(train) >= cfg["minimum_train_games"]
                    and len(test) >= cfg["minimum_test_games"])
        folds.append({"season": int(season), "train_games": len(train), "test_games": len(test),
                      "prior_seasons": nseasons, "evaluated": bool(eligible),
                      "reason": "" if eligible else "insufficient_train_history_or_test_games"})
        if not eligible:
            continue
        assert train.season.max() < test.season.min()
        for spec in specs:
            pred, fit = fit_predict(train, test, spec["features"], cfg["ridge_penalty"])
            p = test[["game_id", "season", "game_day", "decision_utc", "target"]].copy()
            p["model"] = spec["id"]
            p["prediction"] = pred
            p["squared_error"] = (p.target - pred) ** 2
            p["absolute_error"] = (p.target - pred).abs()
            rows.append(p)
            coefficients.append({"model": spec["id"], "test_season": int(season),
                                 "train_max_season": int(train.season.max()), **fit})
    predictions = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return predictions, folds, coefficients, excluded


def paired_comparison(predictions, comparison, cfg, project_count):
    control = predictions[predictions.model.eq(comparison["control"])]
    candidate = predictions[predictions.model.eq(comparison["candidate"])]
    key = ["game_id", "season", "game_day"]
    if set(map(tuple, control[key].to_numpy())) != set(map(tuple, candidate[key].to_numpy())):
        raise ValueError("Compared models have different evaluation games")
    pair = control[key + ["squared_error"]].merge(candidate[key + ["squared_error"]], on=key,
                                                 validate="one_to_one", suffixes=("_control", "_candidate"))
    pair["improvement"] = pair.squared_error_control - pair.squared_error_candidate
    means = pair.groupby("season").improvement.mean()
    n = len(means)
    summary = {"comparison": comparison["id"], "games": len(pair), "validation_seasons": n,
               "mean_season_mse_improvement": float(means.mean()) if n else None,
               "status": "insufficient_validation_seasons", "raw_two_sided_p": None,
               "project_adjusted_p": None, "n_variants_committed": 6, "project_count": project_count}
    if n >= 5:
        se = float(means.std(ddof=1) / np.sqrt(n))
        mu = float(means.mean())
        if se > 0:
            p = float(2 * stats.t.sf(abs(mu / se), df=n-1))
            half = float(stats.t.ppf(1 - 0.05 / (2 * project_count), df=n-1) * se)
        else:
            p, half = (1.0, 0.0) if mu == 0 else (None, None)
        summary.update(status="retrospective_diagnostic", raw_two_sided_p=p,
                       project_adjusted_p=min(1.0, p * project_count) if p is not None else None,
                       project_interval_low=mu-half if half is not None else None,
                       project_interval_high=mu+half if half is not None else None,
                       seasons_positive=int((means > 0).sum()))
        rng = np.random.default_rng(cfg["seed"])
        groups = []
        for _, season in pair.groupby("season"):
            days = season.groupby("game_day").improvement.agg(["sum", "count"]).to_numpy(float)
            groups.append(days)
        boot = []
        for _ in range(cfg["bootstrap_draws"]):
            samples = []
            for i in rng.integers(0, n, size=n):
                days = groups[i]
                draw = days[rng.integers(0, len(days), size=len(days))]
                samples.append(draw[:, 0].sum() / draw[:, 1].sum())
            boot.append(np.mean(samples))
        summary["diagnostic_bootstrap_95_low"], summary["diagnostic_bootstrap_95_high"] = [float(x) for x in np.quantile(boot, [0.025, 0.975])]
    return summary, pair


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=HERE.parent)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing outputs are never overwritten")
    parser.add_argument("--run", action="store_true", help="Read historical outcomes and fit all six fixed specifications")
    parser.add_argument("--expected-protocol-sha256", help="Required with --run; freeze the reviewed protocol")
    parser.add_argument("--project-count", type=int, help="Latest total including these six; never below the setup count")
    args = parser.parse_args(argv)
    cfg = load_protocol()
    protocol_hash = digest(PROTOCOL)
    if args.run and args.expected_protocol_sha256 != protocol_hash:
        parser.error("--run requires the exact reviewed --expected-protocol-sha256")
    if args.run and (args.project_count is None or args.project_count < cfg["project_count_at_setup"]):
        parser.error("--run requires --project-count including all six specifications and any later studies")
    if args.output.exists():
        parser.error("Choose a new output directory; evidence is never overwritten")
    data, exclusions, metadata = make_inputs(args.input_root, cfg)
    args.output.mkdir(parents=True)
    provenance = {"mode": "historical_discovery" if args.run else "outcome_blind_preflight",
                  "protocol_sha256": protocol_hash, "script_sha256": digest(__file__),
                  "setup_specifications": cfg["models"], "project_count": args.project_count,
                  "score_columns_read": bool(args.run), "latest_season": 2025,
                  "inputs": metadata, "historical_confirmation_sample": False,
                  "historical_specifications_evaluated": 0}
    provenance["runtime"] = {"pandas": pd.__version__, "numpy": np.__version__}
    for sport, reject in exclusions.items():
        reject.to_csv(args.output / f"{sport}_forecast_exclusions.csv", index=False)
        d = data[sport]
        d.groupby("season").size().rename("revision_eligible").to_csv(args.output / f"{sport}_coverage.csv")
        if sport == "nfl":
            columns = ["game_id", "season", "decision_utc", "style", "home_prior_n", "away_prior_n",
                       "home_prior_games", "away_prior_games", "home_latest_available_utc", "away_latest_available_utc"]
            d[columns].to_csv(args.output / "nfl_style_feature_audit.csv", index=False)
    if args.run:
        completed, all_predictions, summaries, pairs = [], [], [], []
        labelled_inputs = {sport: attach_outcomes(data[sport], args.input_root, sport, cfg)
                           for sport in ["nfl", "cfb"]}
        provenance["historical_outcome_sha256"] = {
            sport: data_digest(d[["game_id", "season", "target"]]) for sport, d in labelled_inputs.items()}
        for sport, cohort in [("nfl", "revision"), ("cfb", "revision"), ("nfl", "style")]:
            specs = [m for m in cfg["models"] if m["sport"] == sport and m["cohort"] == cohort]
            labelled = labelled_inputs[sport]
            predictions, folds, fits, rejected = walk_forward(labelled, specs, cfg)
            stem = f"{sport}_{cohort}"
            pd.DataFrame(folds).to_csv(args.output / f"{stem}_folds.csv", index=False)
            rejected.to_csv(args.output / f"{stem}_fit_exclusions.csv", index=False)
            (args.output / f"{stem}_coefficients.json").write_text(json.dumps(fits, indent=2)+"\n")
            completed.extend({**m, "evaluated": not predictions.empty} for m in specs)
            if predictions.empty:
                continue
            all_predictions.append(predictions)
            comp = next(c for c in cfg["comparisons"] if c["control"] == specs[0]["id"])
            summary, pair = paired_comparison(predictions, comp, cfg, args.project_count)
            summaries.append(summary)
            pairs.append(pair.assign(comparison=comp["id"]))
        if all_predictions:
            pd.concat(all_predictions, ignore_index=True).to_parquet(args.output / "predictions.parquet", index=False)
            pd.concat(pairs, ignore_index=True).to_csv(args.output / "paired_errors.csv", index=False)
        pd.DataFrame(summaries).to_csv(args.output / "comparisons.csv", index=False)
        provenance["specification_ledger"] = completed
        provenance["historical_specifications_evaluated"] = sum(m["evaluated"] for m in completed)
        assert len(completed) == 6
    (args.output / "protocol.json").write_bytes(PROTOCOL.read_bytes())
    (args.output / "manifest.json").write_text(json.dumps(provenance, indent=2)+"\n")
    report = ["# Forecast revisions and offensive style", "",
              "RETROSPECTIVE DISCOVERY ONLY. Previously examined seasons are not fresh confirmation.",
              "Closing totals are a diagnostic benchmark, not prices available at forecast time. No ROI or live-rule verdict.",
              "", f"Mode: {provenance['mode']}. Six specifications committed; 2026 excluded at the reader boundary.",
              f"Protocol SHA256: {protocol_hash}", "", "## Input coverage", ""]
    report.extend(f"- {sport.upper()}: {v['eligible_revision_rows']} valid forecast pairs; style rows {v['eligible_style_rows']}; exclusions {v['rejections']}"
                  for sport, v in metadata.items() if isinstance(v, dict))
    if args.run:
        report += ["", "## Paired comparisons", ""]
        report.extend(f"- {s['comparison']}: {s['games']} games across {s['validation_seasons']} seasons; season-balanced MSE improvement {s['mean_season_mse_improvement']:.4f}; adjusted p {s['project_adjusted_p']}."
                      for s in summaries)
    else:
        report += ["", "No final scores were read and no historical model was fitted."]
    (args.output / "report.md").write_text("\n".join(report)+"\n")
    print(json.dumps({"mode": provenance["mode"], "specifications": 6, "protocol_sha256": protocol_hash,
                      "coverage": metadata, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
