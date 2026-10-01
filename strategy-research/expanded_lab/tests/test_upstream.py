"""Synthetic tests of the research protocol, temporal boundaries, paired evaluation and I/O."""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / "vendor" / "forecast_style.py"
spec = importlib.util.spec_from_file_location("forecast_style", MODULE)
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


def forecast(season=2020, game="current", kick=None):
    kick = pd.Timestamp(kick or f"{season}-09-15T18:00:00Z")
    day = kick.tz_convert("America/New_York").normalize().tz_localize(None)
    rt = pd.Timestamp(day.date(), tz="UTC") - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
    return dict(game_id=game, season=season, start_utc=kick, home_team="H", away_team="A",
                mos1_mph=12., mos2_mph=8., mos1_runtime=rt, mos2_runtime=rt-pd.Timedelta(days=1))


def history(season=2020):
    return pd.DataFrame([dict(game_id=f"{season}-prior-{day}", season=season,
                             date=pd.Timestamp(f"{season}-09-{day:02d}"), team=team,
                             game_type="REG", pass_rate_sit=0.4+day/100)
                         for team in ["H", "A"] for day in [1, 5, 9]])


def synthetic_root(tmp):
    for sport in ["nfl", "cfb"]:
        p = tmp / f"{sport}-weather/data/processed"
        p.mkdir(parents=True)
        rows = [forecast(), forecast(2026, "sealed")]
        for row in rows:
            row.update(total=38., total_line=44., close_total=44.)
        pd.DataFrame(rows).to_parquet(p / "mos_replay.parquet", index=False)
    history().to_parquet(tmp / "nfl-weather/data/processed/team_games.parquet", index=False)
    return tmp


def test_six_specifications_are_recorded_including_controls():
    cfg = fs.load_protocol()
    assert len(cfg["models"]) == 6
    assert cfg["project_count_at_setup"] == cfg["project_count_before"]+6
    assert len(cfg["comparisons"]) == 3


def test_outcome_blind_preflight_projects_columns_and_filters_sealed_rows(tmp_path, monkeypatch):
    root = synthetic_root(tmp_path / "input")
    original, reads = pd.read_parquet, []
    def spy(path, **kwargs):
        reads.append(kwargs)
        assert kwargs["filters"] == [("season", "<=", 2025)]
        assert not {"total", "total_line", "close_total", "under_win", "profit"} & set(kwargs["columns"])
        return original(path, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", spy)
    out = tmp_path / "out"
    fs.main(["--input-root", str(root), "--output", str(out)])
    assert len(reads) == 3
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["score_columns_read"] is False
    assert manifest["inputs"]["nfl"]["eligible_revision_rows"] == 1
    assert manifest["inputs"]["cfb"]["eligible_revision_rows"] == 1
    assert (out / "report.md").exists()


def test_explicit_outcome_reader_also_filters_before_return(tmp_path, monkeypatch):
    root = synthetic_root(tmp_path / "input")
    cfg = fs.load_protocol()
    d, _ = fs.prepare_forecasts(pd.DataFrame([forecast()]), cfg)
    original, reads = pd.read_parquet, []
    def spy(path, **kwargs):
        reads.append(kwargs)
        assert kwargs["filters"] == [("season", "<=", 2025)]
        return original(path, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", spy)
    labelled = fs.attach_outcomes(d, root, "nfl", cfg)
    assert len(labelled) == 1 and labelled.target.iloc[0] == -6
    assert reads[0]["columns"] == ["game_id", "season", "total", "total_line"]


@pytest.mark.parametrize("kick", ["2020-11-01T18:00:00Z", "2020-03-09T18:00:00Z", "2020-09-15T18:00:00Z"])
def test_decision_clock_and_publication_are_valid_across_dst(kick):
    cfg = fs.load_protocol()
    d, rejected = fs.prepare_forecasts(pd.DataFrame([forecast(kick=kick)]), cfg)
    assert rejected.empty
    row = d.iloc[0]
    assert row.decision_utc.tz_convert("America/Los_Angeles").hour == 19
    assert row.mos1_runtime + pd.Timedelta(hours=5) <= row.decision_utc < row.start_utc
    assert row.revision == 4


def test_late_wrong_date_missing_and_reversed_forecasts_are_logged():
    rows = [forecast(game=f"g{i}") for i in range(4)]
    rows[0]["mos1_runtime"] += pd.Timedelta(days=1)
    rows[1]["mos1_mph"] = np.nan
    rows[2]["mos2_runtime"] = rows[2]["mos1_runtime"]
    # Valid lead-day but too late to publish for a winter 19:30 Pacific decision.
    rows[3] = forecast(game="g3", kick="2020-12-15T18:00:00Z")
    rows[3]["mos1_runtime"] += pd.Timedelta(hours=5)
    kept, rejected = fs.prepare_forecasts(pd.DataFrame(rows), fs.load_protocol())
    assert kept.empty and len(rejected) == 4
    assert set(rejected.reason) == {"forecast_runtime_on_wrong_lead_date", "missing_forecast_or_runtime",
                                    "reversed_forecast_times", "forecast_not_published_by_decision"}


def test_style_excludes_current_future_season_and_not_yet_available_games():
    cfg = fs.load_protocol()
    d, _ = fs.prepare_forecasts(pd.DataFrame([forecast()]), cfg)
    h = history()
    baseline = fs.attach_style(d, h, cfg)
    extra = []
    for team in ["H", "A"]:
        for game, day, season in [("current", 1, 2020), ("late", 14, 2020), ("future", 20, 2020), ("prior-year", 1, 2019)]:
            extra.append(dict(game_id=game, season=season, date=pd.Timestamp(f"2020-09-{day:02d}"),
                              team=team, game_type="REG", pass_rate_sit=1.0))
    changed = fs.attach_style(d, pd.concat([h, pd.DataFrame(extra)], ignore_index=True), cfg)
    assert baseline["style"].iloc[0] == changed["style"].iloc[0]
    assert changed.home_prior_n.iloc[0] == changed.away_prior_n.iloc[0] == 3
    assert changed.home_latest_available_utc.iloc[0] <= changed.decision_utc.iloc[0]


def test_style_requires_three_prior_games_for_each_team():
    cfg = fs.load_protocol()
    d, _ = fs.prepare_forecasts(pd.DataFrame([forecast()]), cfg)
    h = history()
    h = h[~((h.team == "A") & (h.game_id == "2020-prior-9"))]
    out = fs.attach_style(d, h, cfg)
    assert out["style"].isna().all()


def sample_training():
    rows = []
    rng = np.random.default_rng(10)
    for season in range(2000, 2012):
        for i in range(30):
            wind, revision = rng.uniform(0, 25), rng.normal()
            rows.append(dict(game_id=f"{season}-{i:02d}", season=season,
                             game_day=f"{season}-09-{1+i//3:02d}", decision_utc=pd.Timestamp(f"{season}-09-01", tz="UTC"),
                             wind1=wind, revision=revision, target=-0.2*wind+3*revision+rng.normal()))
    return pd.DataFrame(rows)


def test_walk_forward_is_paired_deterministic_and_not_fitted_on_later_seasons():
    cfg = copy.deepcopy(fs.load_protocol())
    cfg.update(minimum_train_games=50, minimum_test_games=10)
    specs = cfg["models"][:2]
    d = sample_training()
    pred, folds, fits, _ = fs.walk_forward(d, specs, cfg)
    assert all(f["train_max_season"] < f["test_season"] for f in fits)
    assert min(pred.season) == 2005
    later = d.copy()
    later.loc[later.season == 2011, "target"] = 1e8
    altered, _, _, _ = fs.walk_forward(later, specs, cfg)
    pd.testing.assert_frame_equal(pred[pred.season <= 2010].reset_index(drop=True),
                                  altered[altered.season <= 2010].reset_index(drop=True))
    shuffled, _, _, _ = fs.walk_forward(d.sample(frac=1, random_state=7), specs, cfg)
    pd.testing.assert_frame_equal(pred, shuffled)
    for _, group in pred.groupby("model"):
        assert len(group) == len(pred)//2


def test_scaling_and_prediction_ignore_test_targets():
    d = sample_training()
    train, test = d[d.season < 2005], d[d.season == 2005]
    first, fit = fs.fit_predict(train, test, ["wind1", "revision"], 10)
    test = test.copy()
    test["target"] = 1e99
    second, changed = fs.fit_predict(train, test, ["wind1", "revision"], 10)
    np.testing.assert_array_equal(first, second)
    assert fit == changed
    np.testing.assert_allclose(fit["mean"], train[["wind1", "revision"]].mean().values)


def test_future_season_cannot_bypass_reader_guard():
    cfg = fs.load_protocol()
    d = sample_training()
    d.loc[0, "season"] = 2026
    with pytest.raises(ValueError, match="Sealed"):
        fs.walk_forward(d, cfg["models"][:2], cfg)


def test_paired_bootstrap_is_repeatable_and_positive_for_planted_improvement():
    cfg = copy.deepcopy(fs.load_protocol())
    cfg.update(minimum_train_games=50, minimum_test_games=10, bootstrap_draws=100)
    pred, _, _, _ = fs.walk_forward(sample_training(), cfg["models"][:2], cfg)
    a, pairs = fs.paired_comparison(pred, cfg["comparisons"][0], cfg, 294)
    b, _ = fs.paired_comparison(pred, cfg["comparisons"][0], cfg, 294)
    assert a == b
    assert a["mean_season_mse_improvement"] > 0
    assert a["project_adjusted_p"] >= a["raw_two_sided_p"]
    assert pairs.improvement.mean() > 0
    removed = pred.drop(pred.index[-1])
    with pytest.raises(ValueError, match="different evaluation games"):
        fs.paired_comparison(removed, cfg["comparisons"][0], cfg, 294)


def test_run_requires_reviewed_protocol_hash_and_current_count(tmp_path):
    with pytest.raises(SystemExit):
        fs.main(["--run", "--output", str(tmp_path/"out")])
    with pytest.raises(SystemExit):
        fs.main(["--run", "--output", str(tmp_path/"out"), "--expected-protocol-sha256", fs.digest(fs.PROTOCOL),
                 "--project-count", "288"])


def test_existing_evidence_is_never_overwritten(tmp_path):
    out = tmp_path/"existing"
    out.mkdir()
    with pytest.raises(SystemExit):
        fs.main(["--output", str(out)])


def test_empty_historical_cohort_is_reported_without_fitting(tmp_path):
    root = synthetic_root(tmp_path/"input")
    for sport in ["nfl", "cfb"]:
        p = root/f"{sport}-weather/data/processed/mos_replay.parquet"
        d = pd.read_parquet(p)
        d.loc[d.season == 2020, "mos1_mph"] = np.nan
        d.to_parquet(p, index=False)
    out = tmp_path/"empty-out"
    fs.main(["--input-root", str(root), "--output", str(out)])
    manifest = json.loads((out/"manifest.json").read_text())
    assert manifest["inputs"]["nfl"]["eligible_revision_rows"] == 0


def test_full_synthetic_cli_records_all_six_models_and_paired_outputs(tmp_path, monkeypatch):
    cfg = copy.deepcopy(fs.load_protocol())
    cfg["bootstrap_draws"] = 20  # synthetic harness only; committed historical setting stays 10,000
    monkeypatch.setattr(fs, "load_protocol", lambda: cfg)
    root = tmp_path/"inputs"
    forecasts = []
    histories = []
    rng = np.random.default_rng(30)
    for season in range(2000, 2013):
        histories.append(history(season))
        for i in range(60):
            kick = pd.Timestamp(f"{season}-09-15T18:00:00Z") + pd.Timedelta(days=i)
            row = forecast(season, f"{season}-{i:02d}", str(kick))
            row["mos1_mph"] = rng.uniform(4, 25)
            row["mos2_mph"] = row["mos1_mph"] + rng.uniform(-4, 4)
            row.update(total=44-0.2*row["mos1_mph"]+rng.normal(), total_line=44., close_total=44.)
            forecasts.append(row)
    for sport in ["nfl", "cfb"]:
        p = root/f"{sport}-weather/data/processed"
        p.mkdir(parents=True)
        pd.DataFrame(forecasts).to_parquet(p/"mos_replay.parquet", index=False)
    pd.concat(histories, ignore_index=True).to_parquet(root/"nfl-weather/data/processed/team_games.parquet", index=False)
    out = tmp_path/"run"
    fs.main(["--input-root", str(root), "--output", str(out), "--run",
             "--expected-protocol-sha256", fs.digest(fs.PROTOCOL), "--project-count", "294"])
    manifest = json.loads((out/"manifest.json").read_text())
    assert len(manifest["specification_ledger"]) == 6
    assert all(m["evaluated"] for m in manifest["specification_ledger"])
    predictions = pd.read_parquet(out/"predictions.parquet")
    assert predictions.model.nunique() == 6
    assert predictions.season.max() <= 2025
    assert len(pd.read_csv(out/"comparisons.csv")) == 3
