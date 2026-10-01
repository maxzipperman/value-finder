import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import simulate as sim
import runner as lab

def frame():
    rng=np.random.default_rng(77)
    d=pd.DataFrame([dict(game_id=f'{s}-{i}',season=s,game_day=f'{s}-09-{i//3+1:02}',
        wind1=rng.uniform(0,30),wind2=rng.uniform(0,30),style=rng.uniform(.3,.7))
        for s in range(2000,2012) for i in range(60)])
    d['revision']=d.wind1-d.wind2;d['wind_style']=d.wind1*d['style']
    return lab.engineer(d)

def test_cached_design_refits_match_individual_ridge_solves():
    cfg=lab.load_protocol();models=cfg['models'][:2]
    item=sim.design(frame(),models,cfg['design'])
    rng=np.random.default_rng(7);y=rng.normal(size=(len(item['frame']),3))
    for fold in item['folds']:
        train=item['frame'].iloc[fold['train']].copy();test=item['frame'].iloc[fold['test']].copy()
        for m in models:
            projection,b=fold['models'][m['id']]
            for rep in range(3):
                train['target']=y[fold['train'],rep]
                expected,_=lab.fs.fit_predict(train,test,m['features'],cfg['design']['ridge_penalty'])
                actual=b@(projection@y[fold['train'],rep])
                np.testing.assert_allclose(actual,expected,rtol=1e-11,atol=1e-11)

def test_holm_and_bh_known_examples():
    p=np.array([[.001,.02,.03,.8],[.2,.4,.6,.8]])
    assert sim.adjust(p,'holm').tolist()==[[True,False,False,False],[False]*4]
    assert sim.adjust(p,'bh').tolist()==[[True,True,True,False],[False]*4]

def test_overlapping_nfl_games_share_identical_simulated_outcomes():
    parent=lab.load_protocol();cfg=json.loads((ROOT/'simulation_protocol.json').read_text());d=frame()
    a=sim.design(d,[m for m in parent['models'] if m['sport']=='nfl' and m['cohort']=='revision'],parent['design'])
    b=sim.design(d.iloc[10:],[m for m in parent['models'] if m['sport']=='nfl' and m['cohort']=='style'],parent['design'])
    ys=sim.joint_targets([a,b],'game_day_plus_season_drift',1.,4,np.random.default_rng(8),cfg)
    loc=pd.Index(a['frame'].game_id).get_indexer(b['frame'].game_id)
    np.testing.assert_array_equal(ys[0][loc],ys[1])

def test_simulation_target_does_not_require_historical_outcomes():
    parent=lab.load_protocol();cfg=json.loads((ROOT/'simulation_protocol.json').read_text())
    item=sim.design(frame(),parent['models'][:2],parent['design'])
    y=sim.synthetic_targets(item,'independent',0.,1000,np.random.default_rng(10),cfg)
    residual=y-item['mean'][:,None]
    assert abs(residual.mean())<.1
    assert 9.9<residual.std()<10.1

def test_wilson_bounds_cover_zero_and_all_successes():
    low,high=sim.interval(0,2000)
    assert abs(low)<1e-12 and high>0
    low,high=sim.interval(2000,2000)
    assert low<1 and abs(high-1)<1e-12
