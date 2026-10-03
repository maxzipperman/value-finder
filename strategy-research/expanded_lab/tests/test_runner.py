import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lab_runner',ROOT/'runner.py')
lab=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

def test_protocol_accounts_for_every_specification_and_comparison():
    cfg=lab.load_protocol(lab.sha(ROOT/'protocol.json'))
    assert len(cfg['models'])==26
    assert sum(m['new_variant'] for m in cfg['models'])==20
    assert len(cfg['comparisons'])==23
    ids={m['id'] for m in cfg['models']}
    assert all(c['candidate'] in ids and c['control'] in ids for c in cfg['comparisons'])

def test_wrong_hash_stops_before_inputs():
    with pytest.raises(ValueError,match='hash'):
        lab.load_protocol('wrong')

def test_fixed_features_handle_threshold_equality_and_direction():
    d=pd.DataFrame(dict(wind1=[15.,14.,17.,0.],wind2=[14.,15.,16.,0.],style=[.5]*4))
    d['revision']=d.wind1-d.wind2
    out=lab.engineer(d)
    assert out.cross_up15.tolist()==[1,0,0,0]
    assert out.cross_down15.tolist()==[0,1,0,0]
    assert out.persistent15.tolist()==[0,0,1,0]
    assert out.revision_up.tolist()==[1,0,1,0]
    assert out.revision_down.tolist()==[0,1,0,0]
    assert out.revision_style.tolist()==[.5,-.5,.5,0]

def synthetic():
    rows=[]
    rng=np.random.default_rng(1)
    for season in range(2000,2015):
        for i in range(75):
            w1,w2=rng.uniform(0,30,2)
            style=rng.uniform(.3,.7)
            rows.append(dict(game_id=f'{season}-{i}',season=season,game_day=f'{season}-09-{i//3+1:02}',
                decision_utc=pd.Timestamp(f'{season}-09-01',tz='UTC'),wind1=w1,wind2=w2,
                revision=w1-w2,style=style,wind_style=w1*style,
                target=-.2*w1+.1*(w1-w2)+rng.normal(0,4)))
    return lab.engineer(pd.DataFrame(rows))

def test_all_26_models_fit_chronologically_and_sealed_changes_cannot_affect_them():
    cfg=lab.load_protocol()
    d=synthetic()
    all_ids=[]
    for sport,cohort in [('nfl','revision'),('cfb','revision'),('nfl','style')]:
        models=[m for m in cfg['models'] if m['sport']==sport and m['cohort']==cohort]
        pred,_,fits,_=lab.fs.walk_forward(d,models,cfg['design'])
        assert all(f['train_max_season']<f['test_season'] for f in fits)
        assert pred.model.nunique()==len(models)
        all_ids.extend(pred.model.unique())
        changed=d.copy()
        changed.loc[changed.season==2014,'target']=1e12
        later,_,_,_=lab.fs.walk_forward(changed,models,cfg['design'])
        pd.testing.assert_frame_equal(pred[pred.season<2014].reset_index(drop=True),later[later.season<2014].reset_index(drop=True))
    assert len(set(all_ids))==26

def test_nested_bootstrap_reproducible_with_day_clusters():
    pair=pd.DataFrame([dict(season=s,game_day=f'{s}-09-{i//2+1}',improvement=1.+i) for s in range(2000,2006) for i in range(10)])
    a=lab.nested_bootstrap(pair,1000,123)
    assert a==lab.nested_bootstrap(pair,1000,123)
    assert a[0]<=pair.improvement.mean()<=a[1]

def test_degenerate_inference_does_not_claim_significance():
    cfg=lab.load_protocol()
    cfg['bootstrap_draws']=100
    rows=[dict(game_id=f'{s}-{i}',season=s,game_day=f'{s}-09-{i+1}',model=m,squared_error=e)
          for s in range(2000,2006) for i in range(5) for m,e in [('base',2.),('candidate',1.)]]
    summary,_=lab.comparison(pd.DataFrame(rows),dict(id='x',control='base',candidate='candidate'),cfg,314)
    assert summary['raw_p'] is None and summary['promotion_allowed'] is False

def test_sign_flip_preserves_joint_model_dependence_and_is_deterministic():
    cfg=lab.load_protocol();cfg['sign_flip_draws']=1000
    pair=pd.DataFrame([dict(season=s,improvement=float(s%3-1)) for s in range(2000,2012)])
    a=lab.selection_diagnostic({'a':pair,'b':pair},cfg)
    assert a==lab.selection_diagnostic({'a':pair,'b':pair},cfg)
    assert a['status']=='approximate_diagnostic_only'

def test_runner_rejects_outputs_outside_isolated_lab():
    with pytest.raises(SystemExit):
        lab.main(['preflight','--run-dir','/private/tmp/not-in-lab'])

def test_missing_run_hash_stops_before_outcomes():
    with pytest.raises(SystemExit):
        lab.main(['run'])
