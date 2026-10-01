"""Full refit calibration and power study; predictor-only, offline, resumable."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy import stats
import runner as lab

HERE=Path(__file__).resolve().parent

def design(frame,specs,cfg):
    features=sorted({f for m in specs for f in m['features']})
    d=frame[np.isfinite(frame[features].to_numpy(float)).all(axis=1)].sort_values(['season','game_id']).reset_index(drop=True)
    folds=[]
    for season in sorted(d.season.unique()):
        tr=np.flatnonzero((d.season<season).to_numpy());te=np.flatnonzero((d.season==season).to_numpy())
        if d.iloc[tr].season.nunique()<cfg['minimum_prior_seasons'] or len(tr)<cfg['minimum_train_games'] or len(te)<cfg['minimum_test_games']:
            continue
        models={}
        for m in specs:
            x=d.iloc[tr][m['features']].to_numpy(float);xt=d.iloc[te][m['features']].to_numpy(float)
            mu=x.mean(axis=0);sd=x.std(axis=0);sd[sd<1e-12]=1
            a=np.column_stack([np.ones(len(x)),(x-mu)/sd]);b=np.column_stack([np.ones(len(xt)),(xt-mu)/sd])
            reg=np.diag([0.]+[cfg['ridge_penalty']]*len(m['features']))
            # Applying this to a new y refits every coefficient, with train-only scaling.
            projection=np.linalg.solve(a.T@a+reg,a.T)
            models[m['id']]=(projection,b)
        folds.append(dict(season=int(season),train=tr,test=te,models=models))
    initial=d[d.season.isin(sorted(d.season.unique())[:5])]
    a=np.column_stack([np.ones(len(initial)),initial.wind1.to_numpy(float)])
    coef=np.linalg.lstsq(a,initial.revision.to_numpy(float),rcond=None)[0]
    residual=d.revision.to_numpy(float)-(coef[0]+coef[1]*d.wind1.to_numpy(float))
    initial_residual=initial.revision.to_numpy(float)-a@coef
    scale=float(initial_residual.std())
    if scale<=1e-12:
        raise ValueError('No variation in the initial revision signal')
    days=pd.factorize(d.game_day)[0];seasons=pd.factorize(d.season)[0]
    mean=-.2*d.wind1.to_numpy(float)
    return dict(frame=d,folds=folds,effect=residual/scale,mean=mean,days=days,seasons=seasons,specs=specs)

def synthetic_targets(item,regime,effect,size,rng,cfg):
    n=len(item['frame']);scale=cfg['noise_scale_points']
    def noise(shape):
        if regime=='independent':
            return rng.normal(size=shape)
        df=cfg['student_t_degrees_of_freedom']
        return rng.standard_t(df,size=shape)/np.sqrt(df/(df-2))
    day_share=0 if regime=='independent' else cfg['same_day_noise_share']
    season_share=cfg['season_noise_share'] if regime=='game_day_plus_season_drift' else 0
    z=np.sqrt(1-day_share-season_share)*noise((n,size))
    if day_share:
        z+=np.sqrt(day_share)*noise((item['days'].max()+1,size))[item['days']]
    if season_share:
        z+=np.sqrt(season_share)*noise((item['seasons'].max()+1,size))[item['seasons']]
    return item['mean'][:,None]+effect*item['effect'][:,None]+scale*z

def joint_targets(items,regime,effect,size,rng,cfg):
    sources={};output=[]
    for item in items:
        sport=item['specs'][0]['sport']
        if sport not in sources:
            y=synthetic_targets(item,regime,effect,size,rng,cfg)
            sources[sport]=(pd.Index(item['frame'].game_id),y)
        else:
            index,ybase=sources[sport]
            loc=index.get_indexer(item['frame'].game_id)
            if (loc<0).any():
                raise ValueError('Shared-sport cohorts need identical synthetic game outcomes')
            y=ybase[loc]
        output.append(y)
    return output

def refit_statistics(item,y,comparisons):
    by_comparison={c['id']:[] for c in comparisons}
    for fold in item['folds']:
        loss={}
        for mid,(projection,test_design) in fold['models'].items():
            coefficients=projection@y[fold['train']]
            prediction=test_design@coefficients
            loss[mid]=((y[fold['test']]-prediction)**2).mean(axis=0)
        for c in comparisons:
            by_comparison[c['id']].append(loss[c['control']]-loss[c['candidate']])
    output={}
    for name,rows in by_comparison.items():
        x=np.asarray(rows)
        if len(x)<5:
            raise ValueError('Too few validation seasons in the simulation')
        mu=x.mean(axis=0);se=x.std(axis=0,ddof=1)/np.sqrt(len(x))
        t=np.divide(mu,se,out=np.zeros_like(mu),where=se>1e-12)
        p=2*stats.t.sf(abs(t),len(x)-1)
        output[name]=(t,p)
    return output

def adjust(p,method,q=.05):
    order=np.argsort(p,axis=1);sorted_p=np.take_along_axis(p,order,axis=1)
    m=p.shape[1]
    if method=='holm':
        adjusted=np.maximum.accumulate(sorted_p*(m-np.arange(m)),axis=1)
    else:
        adjusted=np.minimum.accumulate((sorted_p*m/np.arange(1,m+1))[:,::-1],axis=1)[:,::-1]
    selected=adjusted<=q
    result=np.zeros_like(selected)
    np.put_along_axis(result,order,selected,axis=1)
    return result

def interval(k,n):
    p=k/n;z=1.959963984540054
    den=1+z*z/n;mid=(p+z*z/(2*n))/den
    half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [float(mid-half),float(mid+half)]

def cell_job(task):
    lab.guard()
    items,parent,cfg,regime,effect,replicates,seed,threshold,out=task
    rng=np.random.default_rng(seed)
    names=[c['id'] for c in parent['comparisons']]
    p_rows=[];t_rows=[];start=time.monotonic()
    for offset in range(0,replicates,cfg['batch_size']):
        size=min(cfg['batch_size'],replicates-offset);result={}
        targets=joint_targets(items,regime,effect,size,rng,cfg)
        for item,y in zip(items,targets):
            mids={m['id'] for m in item['specs']}
            comps=[c for c in parent['comparisons'] if c['candidate'] in mids]
            result.update(refit_statistics(item,y,comps))
        t_rows.append(np.column_stack([result[n][0] for n in names]))
        p_rows.append(np.column_stack([result[n][1] for n in names]))
    t=np.concatenate(t_rows);p=np.concatenate(p_rows)
    positive=t>0
    if threshold is None:
        result=dict(regime=regime,phase='null_calibration',replicates=replicates,
            calibrated_max_t=float(np.quantile(t.max(axis=1),.95)),seed=seed,
            elapsed_seconds=round(time.monotonic()-start,2))
    else:
        masks=dict(global_bonferroni_314=(p<.05/314)&positive,
            prospective_family_holm_23=adjust(p,'holm')&positive,
            prospective_family_bh_05=adjust(p,'bh',.05)&positive,
            prospective_family_bh_10=adjust(p,'bh',.10)&positive,
            prospective_family_calibrated_max_t=(t>threshold))
        designated=[names.index(n) for n in ['NFL_REVISION','CFB_REVISION']]
        metrics=[]
        for method,mask in masks.items():
            any_count=int(mask.any(axis=1).sum());detected=int(mask[:,designated].any(axis=1).sum())
            metrics.append(dict(method=method,probability_any_selection=any_count/replicates,
                probability_interval=interval(any_count,replicates),mean_number_selected=float(mask.sum(axis=1).mean()),
                designated_revision_detection_probability=detected/replicates,
                designated_interval=interval(detected,replicates)))
        result=dict(regime=regime,phase='evaluation',effect_points=effect,replicates=replicates,
            seed=seed,metrics=metrics,elapsed_seconds=round(time.monotonic()-start,2))
    lab.save_json(Path(out),result)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol-hash',required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--pilot',action='store_true',help='Synthetic validation: 32 replicates per cell; not the full study')
    args=parser.parse_args(argv)
    path=HERE/'simulation_protocol.json'
    if lab.sha(path)!=args.protocol_hash:
        parser.error('Simulation protocol hash changed')
    cfg=json.loads(path.read_text());parent=lab.load_protocol(cfg['parent_protocol_sha256'])
    out=args.run_dir.resolve()
    if not out.is_relative_to(HERE/'runs'):
        parser.error('Simulation outputs must stay in the lab')
    lab.guard();out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();identity=dict(protocol_sha256=lab.sha(path),code_sha256=lab.sha(__file__),
        parent_sha256=cfg['parent_protocol_sha256'],pilot=args.pilot,latest_season=2025,outcomes_read=False)
    manifest=out/'simulation_manifest.json'
    prior=json.loads(manifest.read_text()) if manifest.exists() else None
    if prior and any(prior.get(k)!=v for k,v in identity.items()):
        raise ValueError('Cannot resume changed simulation')
    lab.save_json(manifest,dict(**identity,status='loading_predictors'))
    (out/'simulation_protocol.json').write_bytes(path.read_bytes())
    data,_,metadata=lab.fs.make_inputs('/Users/maxzipperman/code/value-finder',parent['design'])
    hashes={sport:lab.fs.data_digest(d) for sport,d in data.items()}
    if prior and prior.get('input_hashes')!=hashes:
        raise ValueError('Historical predictors changed')
    items=[]
    for sport,cohort in [('nfl','revision'),('cfb','revision'),('nfl','style')]:
        models=[m for m in parent['models'] if m['sport']==sport and m['cohort']==cohort]
        items.append(design(lab.engineer(data[sport]),models,parent['design']))
    count=32 if args.pilot else cfg['evaluation_replicates_per_cell']
    calcount=32 if args.pilot else cfg['calibration_replicates_per_regime']
    context=multiprocessing.get_context('spawn')
    # Worker chunks are deterministic and saved independently for restart.
    completed=[]
    for ri,regime in enumerate(cfg['noise_regimes']):
        calpath=out/(regime+'_calibration.json')
        if calpath.exists():
            cal=json.loads(calpath.read_text())
        else:
            cal=cell_job((items,parent,cfg,regime,0.,calcount,cfg['seed']+ri*100,None,str(calpath)))
        completed.append(cal)
        tasks=[]
        for ei,effect in enumerate(cfg['effect_points_per_revision_sd']):
            dest=out/(regime+'_effect_'+str(effect)+'.json')
            if dest.exists():
                completed.append(json.loads(dest.read_text()))
            else:
                tasks.append((items,parent,cfg,regime,effect,count,cfg['seed']+ri*100+ei+1,cal['calibrated_max_t'],str(dest)))
        lab.save_json(manifest,dict(**identity,status='running',input_hashes=hashes,completed_cells=len(completed),regime=regime))
        with ProcessPoolExecutor(max_workers=cfg['workers'],mp_context=context) as pool:
            for result in pool.map(cell_job,tasks):
                completed.append(result)
                lab.save_json(manifest,dict(**identity,status='running',input_hashes=hashes,completed_cells=len(completed),regime=regime))
                print(json.dumps(dict(regime=regime,effect=result['effect_points'],completed_cells=len(completed))),flush=True)
    rows=[]
    for cell in completed:
        if cell['phase']=='evaluation':
            for metric in cell['metrics']:
                rows.append(dict(regime=cell['regime'],effect_points=cell['effect_points'],replicates=cell['replicates'],**metric))
    pd.DataFrame(rows).to_csv(out/'threshold_comparison.csv',index=False)
    lab.save_json(manifest,dict(**identity,status='completed',input_hashes=hashes,completed_cells=len(completed),
        elapsed_seconds=round(time.monotonic()-start,2),total_synthetic_searches=len(cfg['noise_regimes'])*(calcount+len(cfg['effect_points_per_revision_sd'])*count)))
    print(str(out),flush=True)

if __name__=='__main__':
    main()
