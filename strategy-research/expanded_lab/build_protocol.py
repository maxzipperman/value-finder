"""Record a bounded discovery batch before looking at outcomes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def build():
    base = json.loads((HERE / 'vendor/forecast_style_protocol.json').read_text())
    models = [dict(m, origin='existing-six-model-study', new_variant=False) for m in base['models']]
    comparisons = list(base['comparisons'])
    for sport in ['nfl', 'cfb']:
        prefix = sport.upper() + '_REV_'
        features = [
            ('CURVE', ['wind1', 'wind_sq']),
            ('REV_CURVE', ['wind1', 'revision', 'wind_sq']),
            ('ASYMMETRY', ['wind1', 'revision_up', 'revision_down']),
            ('PERSISTENCE', ['wind1', 'persistent15']),
            ('CROSSINGS', ['wind1', 'cross_up15', 'cross_down15']),
            ('REV_INTERACTION', ['wind1', 'revision', 'wind_revision']),
            ('PREVIOUS', ['wind1', 'wind2', 'persistent15']),
            ('COMBINED', ['wind1', 'wind_sq', 'revision_up', 'revision_down', 'persistent15']),
        ]
        for name, fs in features:
            mid = prefix + name
            models.append(dict(id=mid, sport=sport, cohort='revision', features=fs,
                               new_variant=True, origin='research-lab-v1'))
            comparisons.append(dict(id=mid, control=prefix+'BASE', candidate=mid))
    for name, fs in [
        ('REVISION', ['wind1', 'style', 'revision', 'wind_revision']),
        ('CURVE', ['wind1', 'style', 'wind_sq', 'wind_style']),
        ('PERSISTENCE', ['wind1', 'style', 'persistent15', 'persistence_style']),
        ('REV_STYLE', ['wind1', 'style', 'revision', 'wind_style', 'revision_style']),
    ]:
        mid = 'NFL_STYLE_' + name
        models.append(dict(id=mid, sport='nfl', cohort='style', features=fs,
                           new_variant=True, origin='research-lab-v1'))
        comparisons.append(dict(id=mid, control='NFL_STYLE_ADD', candidate=mid))
    return dict(id='value-finder-research-lab-2026-09-30-v1',
        interpretation='Retrospective discovery only; no fresh confirmation, executable-price or ROI claim.',
        latest_season=2025, prior_project_count_at_snapshot=294, new_specifications=20,
        conservative_project_count_floor=314, models=models, comparisons=comparisons,
        upstream_source_commit='f3b56b31aadff4e0c17bf8f8f5c102e21c09c840',
        upstream_code_sha256=hashlib.sha256((HERE/'vendor/forecast_style.py').read_bytes()).hexdigest(),
        upstream_protocol_sha256=hashlib.sha256((HERE/'vendor/forecast_style_protocol.json').read_bytes()).hexdigest(),
        design=base, bootstrap_draws=50000, sign_flip_draws=100000, seed=20260930,
        uncertainty='Two-sided t inference on equally weighted held-out season means; Bonferroni against the project count. Nested season/day bootstrap is diagnostic only.',
        selection_diagnostic='Joint season sign flips across all paired improvements, centered at zero; approximate diagnostic, not a full null refit or a new adoption gate.',
        cohort_policy='Within each sport/cohort, all models see the union-feature complete-case sample. Baselines are rerun on that same sample.',
        minimum_inference_seasons=5, local_trial_ledger=True,
        global_ledger_status='20 additional specifications recorded locally before results; reconcile with the hub before any promotion.',
        frozen_features=dict(wind_sq='wind1 squared', revision_up='max(wind1-wind2,0)',
            revision_down='max(wind2-wind1,0)', persistent15='both winds >=15',
            cross_up15='wind2 <15 and wind1 >=15', cross_down15='wind2 >=15 and wind1 <15',
            wind_revision='wind1 times revision', persistence_style='persistent15 times style',
            revision_style='revision times style'),
        future_stages=[
            dict(id='market_response', status='awaiting timestamped historical odds and separate frozen protocol'),
            dict(id='college_uncertainty', status='awaiting availability-date audit and separate frozen protocol'),
            dict(id='price_engine_robustness', status='awaiting odds cache and separate frozen protocol'),
            dict(id='github_parser_crosscheck', status='independent input audit; not implemented in this batch'),
        ])

if __name__ == '__main__':
    dest=HERE/'protocol.json'
    if dest.exists():
        raise SystemExit('Protocol already exists; create a new version instead of replacing it.')
    dest.write_text(json.dumps(build(),indent=2)+'\n')
    print(hashlib.sha256(dest.read_bytes()).hexdigest())
