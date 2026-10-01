"""Resumable, offline historical discovery. All output stays in this lab."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'vendor/forecast_style.py'
spec=importlib.util.spec_from_file_location('forecast_style',SOURCE)
fs=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path,data):
    tmp=Path(str(path)+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    tmp.replace(path)

def guard():
    """Deny networking, credentials/forward ledgers, and writes outside the isolated lab."""
    def audit(event,args):
        if event.startswith('socket.') or event in {'subprocess.Popen','os.system'}:
            raise PermissionError('Offline lab: networking and subprocesses are disabled')
        if event == 'open':
            path,mode,flags=args
            if isinstance(path,(str,bytes,os.PathLike)):
                p=Path(os.fsdecode(path)).resolve()
                if p.name.startswith('.env') or '.kaggle' in p.parts or 'forward' in p.parts:
                    raise PermissionError('Credentials and forward data are outside this study')
                writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
                if writing and not p.is_relative_to(HERE):
                    raise PermissionError('Research writes must stay inside the lab')
        if event in {'os.rename','os.remove','os.mkdir','os.rmdir','os.chmod','os.link','os.symlink'}:
            paths=args[:2] if event in {'os.rename','os.link','os.symlink'} else args[:1]
            for p in paths:
                if isinstance(p,(str,bytes,os.PathLike)) and not Path(os.fsdecode(p)).resolve().is_relative_to(HERE):
                    raise PermissionError('Filesystem mutation outside the lab is disabled')
    sys.addaudithook(audit)

def load_protocol(expected=None):
    path=HERE/'protocol.json'
    cfg=json.loads(path.read_text())
    if expected and sha(path)!=expected:
        raise ValueError('Frozen protocol hash does not match')
    if cfg['latest_season']!=2025 or cfg['design']['latest_season']!=2025:
        raise ValueError('2026 must remain sealed')
    models=cfg['models']
    if len(models)!=26 or len({m['id'] for m in models})!=26 or sum(m['new_variant'] for m in models)!=20:
        raise ValueError('Specification ledger mismatch')
    if sha(SOURCE)!=cfg['upstream_code_sha256'] or sha(HERE/'vendor/forecast_style_protocol.json')!=cfg['upstream_protocol_sha256']:
        raise ValueError('Pinned upstream code or protocol changed')
    return cfg

def engineer(d):
    d=d.copy()
    d['wind_sq']=d.wind1**2
    d['revision_up']=d.revision.clip(lower=0)
    d['revision_down']=(-d.revision).clip(lower=0)
    d['persistent15']=((d.wind1>=15)&(d.wind2>=15)).astype(float)
    d['cross_up15']=((d.wind2<15)&(d.wind1>=15)).astype(float)
    d['cross_down15']=((d.wind2>=15)&(d.wind1<15)).astype(float)
    d['wind_revision']=d.wind1*d.revision
    if 'style' in d:
        d['persistence_style']=d.persistent15*d['style']
        d['revision_style']=d.revision*d['style']
    return d

def nested_bootstrap(pair,draws,seed):
    rng=np.random.default_rng(seed)
    groups=[s.groupby('game_day').improvement.agg(['sum','count']).to_numpy(float)
            for _,s in pair.groupby('season')]
    n=len(groups)
    if not n:
        return [None,None]
    result=[]
    # Bound temporary arrays: batch at most 256 draws; days stay intact.
    for start in range(0,draws,256):
        size=min(256,draws-start)
        selected=rng.integers(0,n,size=(size,n))
        values=np.zeros((size,n))
        for i,days in enumerate(groups):
            loc=np.argwhere(selected==i)
            if not len(loc):
                continue
            picks=rng.integers(0,len(days),size=(len(loc),len(days)))
            totals=days[picks].sum(axis=1)
            values[loc[:,0],loc[:,1]]=totals[:,0]/totals[:,1]
        result.extend(values.mean(axis=1))
    return [float(x) for x in np.quantile(result,[.025,.975])]

def comparison(predictions,comp,cfg,count):
    key=['game_id','season','game_day']
    a=predictions[predictions.model.eq(comp['control'])]
    b=predictions[predictions.model.eq(comp['candidate'])]
    if set(map(tuple,a[key].to_numpy()))!=set(map(tuple,b[key].to_numpy())):
        raise ValueError('Unpaired evaluation games')
    pair=a[key+['squared_error']].merge(b[key+['squared_error']],on=key,
        validate='one_to_one',suffixes=('_control','_candidate'))
    pair['improvement']=pair.squared_error_control-pair.squared_error_candidate
    means=pair.groupby('season').improvement.mean()
    n=len(means)
    mu=float(means.mean()) if n else None
    se=float(means.std(ddof=1)/np.sqrt(n)) if n>1 else None
    p=float(2*stats.t.sf(abs(mu/se),n-1)) if n>=cfg['minimum_inference_seasons'] and se and se>0 else None
    low,high=nested_bootstrap(pair,cfg['bootstrap_draws'],cfg['seed']) if n>=5 else [None,None]
    out=dict(comparison=comp['id'],candidate=comp['candidate'],control=comp['control'],games=len(pair),
        seasons=n,mean_season_mse_improvement=mu,positive_seasons=int((means>0).sum()),
        raw_p=p,project_adjusted_p=min(1,p*count) if p is not None else None,
        diagnostic_bootstrap_low=low,diagnostic_bootstrap_high=high,
        worst_leave_one_season_out=float(min(means.drop(s).mean() for s in means.index)) if n>1 else None,
        status='retrospective_discovery' if p is not None else 'insufficient_or_degenerate_inference',
        promotion_allowed=False)
    return out,pair

def cohort_job(task):
    # A spawned worker imports the same code and installs its own guard.
    guard()
    frame,specs,cfg,count,dest=task
    dest=Path(dest)
    dest.mkdir(parents=True,exist_ok=True)
    predictions,folds,fits,rejected=fs.walk_forward(frame,specs,cfg['design'])
    pd.DataFrame(folds).to_csv(dest/'folds.csv',index=False)
    rejected.to_csv(dest/'excluded.csv',index=False)
    save_json(dest/'coefficients.json',fits)
    summaries=[]
    if not predictions.empty:
        predictions.to_parquet(dest/'predictions.parquet',index=False)
        for comp in cfg['comparisons']:
            if comp['candidate'] not in {m['id'] for m in specs}:
                continue
            result,pair=comparison(predictions,comp,cfg,count)
            pair.to_csv(dest/(comp['id']+'_paired.csv'),index=False)
            summaries.append(result)
    save_json(dest/'checkpoint.json',dict(status='completed',models=[m['id'] for m in specs],
        evaluated=not predictions.empty,summaries=summaries))
    return summaries

def selection_diagnostic(pairs,cfg):
    """Joint sign flips of aligned season means; preserve within-season model dependence."""
    wide=pd.concat([p.groupby('season').improvement.mean().rename(name) for name,p in pairs.items()],axis=1)
    complete=wide.dropna()
    if len(complete)<5:
        return dict(status='insufficient_common_seasons',common_seasons=len(complete))
    x=complete.to_numpy(float)
    rng=np.random.default_rng(cfg['seed']+1)
    maxima=[]
    n=len(x)
    for start in range(0,cfg['sign_flip_draws'],512):
        batch=min(512,cfg['sign_flip_draws']-start)
        signs=rng.choice([-1.,1.],size=(batch,n))
        z=signs[:,:,None]*x[None,:,:]
        se=z.std(axis=1,ddof=1)/np.sqrt(n)
        t=np.divide(z.mean(axis=1),se,out=np.zeros_like(se),where=se>1e-12)
        maxima.extend(t.max(axis=1))
    return dict(status='approximate_diagnostic_only',common_seasons=n,comparisons=len(complete.columns),
        draws=cfg['sign_flip_draws'],max_t_95=float(np.quantile(maxima,.95)),
        warning='Symmetry assumed. Not a full null refit, global multiple-testing replacement, or promotion criterion.')

def report(out,manifest,summaries):
    ordered=sorted(summaries,key=lambda x:x['mean_season_mse_improvement'] if x['mean_season_mse_improvement'] is not None else -np.inf,reverse=True)
    lines=['# Value Finder research lab','',
        'Historical discovery through 2025. 2026 remains sealed. No strategy is approved by this report.',
        'Target: actual points minus the closing total. This tests scoring information relative to the close; it does not test available entry prices, CLV, or profit.','',
        f"Status: {manifest['status']}. Twenty new specifications recorded locally; six existing controls/models reused.",
        f"Project-count floor for adjustment: {manifest['project_count']}. Reconcile the 20 new trials with the hub before promotion.",'',
        '| Comparison | Games | Seasons | MSE improvement | Positive seasons | Adjusted p |',
        '|---|---:|---:|---:|---:|---:|']
    for s in ordered:
        mu=s['mean_season_mse_improvement']; p=s['project_adjusted_p']
        lines.append(f"| {s['comparison']} | {s['games']} | {s['seasons']} | {mu:.4f} | {s['positive_seasons']} | {p:.6g} |" if p is not None else f"| {s['comparison']} | {s['games']} | {s['seasons']} | {mu} | {s['positive_seasons']} | unavailable |")
    lines += ['','Positive improvement means lower prediction error than the paired baseline. Every validation season has equal weight.',
        'Previously explored historical seasons are not untouched confirmation. Bootstrap intervals and leave-one-season-out results are diagnostics, not extra selection gates.','',
        'Next stages: timestamped-price evaluation, college input-availability audit, and price-engine robustness each need their own frozen specification list.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['preflight','run','resume'])
    parser.add_argument('--input-root',type=Path,default=Path('/Users/maxzipperman/code/value-finder'))
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--protocol-hash')
    parser.add_argument('--prior-project-count',type=int,default=294)
    parser.add_argument('--workers',type=int,default=2,choices=[1,2])
    args=parser.parse_args(argv)
    cfg=load_protocol(args.protocol_hash)
    if args.mode!='preflight' and not args.protocol_hash:
        parser.error('Outcome runs require --protocol-hash')
    if args.prior_project_count<cfg['prior_project_count_at_snapshot']:
        parser.error('Project count cannot be smaller than the known count')
    out=(args.run_dir or HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')).resolve()
    if not out.is_relative_to(HERE/'runs'):
        parser.error('Run directory must be inside the lab runs folder')
    if args.mode=='resume' and not (out/'manifest.json').exists():
        parser.error('Resume requires an existing run manifest')
    if args.mode!='resume' and out.exists():
        parser.error('Existing evidence cannot be overwritten; use resume or a new directory')
    guard()
    out.mkdir(parents=True,exist_ok=True)
    t=time.monotonic()
    count=args.prior_project_count+cfg['new_specifications']
    manifest=dict(status='preflight',mode=args.mode,protocol_sha256=sha(HERE/'protocol.json'),
        runner_sha256=sha(__file__),project_count=count,latest_season=2025,
        new_specifications=20,reused_specifications=6,outcomes_read=False,inputs={},workers=args.workers,
        global_ledger_status=cfg['global_ledger_status'],historical_confirmation=False)
    prior=json.loads((out/'manifest.json').read_text()) if args.mode=='resume' else None
    if prior and any(prior[k]!=manifest[k] for k in ['protocol_sha256','runner_sha256','project_count']):
        raise ValueError('Cannot resume with changed code, protocol or trial count')
    save_json(out/'manifest.json',manifest)
    # Snapshot the complete trial list BEFORE any outcome is read.
    (out/'protocol.json').write_bytes((HERE/'protocol.json').read_bytes())
    save_json(out/'trial_ledger.json',dict(new_trials=[m for m in cfg['models'] if m['new_variant']],
        reused_trials=[m for m in cfg['models'] if not m['new_variant']],counted_even_if_failed=True))
    try:
        data,rejects,metadata=fs.make_inputs(args.input_root,cfg['design'])
        manifest['inputs']=metadata
        for sport,rejected in rejects.items():
            rejected.to_csv(out/(sport+'_forecast_exclusions.csv'),index=False)
            data[sport].groupby('season').size().to_csv(out/(sport+'_coverage.csv'))
        historical_inputs={sport:fs.data_digest(d) for sport,d in data.items()}
        if prior and prior.get('historical_input_hashes')!=historical_inputs:
            raise ValueError('Historical inputs changed; start a new run')
        manifest['historical_input_hashes']=historical_inputs
        save_json(out/'manifest.json',manifest)
        if args.mode=='preflight':
            manifest['status']='preflight_completed'
            save_json(out/'manifest.json',manifest)
            print(json.dumps(dict(output=str(out),status=manifest['status'],coverage=metadata),indent=2))
            return
        labelled={sport:engineer(fs.attach_outcomes(d,args.input_root,sport,cfg['design'])) for sport,d in data.items()}
        outcome_hashes={sport:fs.data_digest(d[['game_id','season','target']]) for sport,d in labelled.items()}
        if prior and prior.get('outcome_hashes')!=outcome_hashes:
            raise ValueError('Historical outcomes changed; start a new run')
        manifest.update(status='running',outcomes_read=True,outcome_hashes=outcome_hashes)
        save_json(out/'manifest.json',manifest)
        tasks=[]; summaries=[]
        for sport,cohort in [('nfl','revision'),('cfb','revision'),('nfl','style')]:
            specs=[m for m in cfg['models'] if m['sport']==sport and m['cohort']==cohort]
            dest=out/(sport+'_'+cohort)
            checkpoint=dest/'checkpoint.json'
            if args.mode=='resume' and checkpoint.exists():
                summaries.extend(json.loads(checkpoint.read_text())['summaries'])
            else:
                tasks.append((labelled[sport],specs,cfg,count,str(dest)))
        # Spawn workers; limits prevent interfering with scheduled jobs.
        if args.workers==1:
            for task in tasks:
                summaries.extend(cohort_job(task))
        else:
            import multiprocessing
            with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn')) as pool:
                for result in pool.map(cohort_job,tasks):
                    summaries.extend(result)
        pd.DataFrame(summaries).to_csv(out/'leaderboard.csv',index=False)
        pairs={p.stem.removesuffix('_paired'):pd.read_csv(p) for p in out.glob('*/*_paired.csv')}
        save_json(out/'selection_diagnostic.json',selection_diagnostic(pairs,cfg))
        manifest.update(status='completed',elapsed_seconds=round(time.monotonic()-t,2),comparisons_completed=len(summaries))
        report(out,manifest,summaries)
        save_json(out/'manifest.json',manifest)
        print(json.dumps(dict(output=str(out),status='completed',comparisons=len(summaries),elapsed_seconds=manifest['elapsed_seconds']),indent=2))
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=type(exc).__name__+': '+str(exc),elapsed_seconds=round(time.monotonic()-t,2))
        save_json(out/'manifest.json',manifest)
        raise

if __name__=='__main__':
    main()
