"""Read-only source-bound certainty inputs and pre-draw attainable gate report."""
from collections import Counter, defaultdict
from fractions import Fraction
import json
import capture
from bounds import attainable
from planner import frame_rows


def load_inputs(frame_path, map_path, contract_path, *, frame_sha256, map_sha256, contract_sha256):
    values=[]
    for path,expected in ((frame_path,frame_sha256),(map_path,map_sha256),(contract_path,contract_sha256)):
        raw=capture.regular(path)
        if capture.digest(raw)!=expected:raise ValueError('published certainty input differs from approved message pin')
        values.append(json.loads(raw))
    frame_rows(values[0])
    return tuple(values)


def pre_draw(frame, *, projected_cohort_costs=None):
    """Use fixed unknown-cohort bounds; report-only, never seed/sample/authorize.

    Default cost projection is deliberately gross:60 per older unknown game or122
    per props unknown game including two metadata calls. Pass an authenticated
    exact cohort cost map when deduplicated original slots/cells are established.
    """
    groups=defaultdict(Counter)
    for row in frame_rows(frame):groups[row['stratum']][row['classification']]+=1
    if projected_cohort_costs is not None and set(projected_cohort_costs)!=set(groups):
        raise ValueError('complete stratum cost map required')
    report=[]
    for key,c in sorted(groups.items()):
        parts=key.split('/')
        if len(parts)!=3 or parts[0] not in ('older','props') or parts[1] not in ('americanfootball_nfl','americanfootball_ncaaf'):
            raise ValueError('unknown primary stratum')
        kind=parts[0];allowed=(2020,2021,2022) if kind=='older' else (2023,2024,2025)
        if int(parts[2]) not in allowed:raise ValueError('season outside stratum')
        sample=min(30 if kind=='older' else 50,c['unknown'])
        cost=(60 if kind=='older' else 122)*c['unknown'] if projected_cohort_costs is None else projected_cohort_costs[key]
        result=attainable(known_successes=c['success'],known_failures=c['failure'],unknown=c['unknown'],sample=sample,phase='existing',
                          projected_new_credits=cost,utility_floor=Fraction(3,5) if kind=='older' else Fraction(1,2),cost_ceiling=100 if kind=='older' else 244)
        report.append(dict(result,stratum=key,known_successes=c['success'],known_failures=c['failure'],projected_new_credits=cost,
                           cost_basis='gross_per_unknown_game' if projected_cohort_costs is None else 'provided_exact_cohort_map'))
    return report


def json_ready(value):
    if isinstance(value,Fraction):return {'numerator':value.numerator,'denominator':value.denominator}
    if isinstance(value,dict):return {k:json_ready(v) for k,v in value.items()}
    if isinstance(value,list):return [json_ready(v) for v in value]
    return value
