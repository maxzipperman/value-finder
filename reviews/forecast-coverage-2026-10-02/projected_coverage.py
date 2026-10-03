"""Aggregate private forecast-availability projections, never forecasts/outcomes.

Input is the exact CSV projection emitted by the October 2 metadata audit.
Only 2023–25 schedules and boolean metadata are accepted. No network, cache
reader, price/outcome join, fits or grading. Outputs contain season aggregates.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

BASE = ('venue_mapped', 'venue_unknown', 'indoor', 'roof_unknown', 'roof_open', 'tbd', 'fbs', 'neutral')
COVERAGE = tuple(f'{kind}_day{n}' for n in (1, 2, 3) for kind in ('mos', 'prev')) + tuple(
    f'{kind}_T{lead}' for lead in ('72', '48', '24', '6', '1', '0.16666666666666666')
    for kind in ('mos', 'mos_covering')) + ('prev_cache_present', 'prev_complete_four_hours')
COLUMNS = {'game_id', 'season', *BASE, *COVERAGE}


def aggregate(path):
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames) != len(COLUMNS) or set(reader.fieldnames) != COLUMNS:
            raise ValueError('Only the exact metadata projection schema is allowed')
        rows = []
        ids = set()
        for r in reader:
            if set(r) != COLUMNS or any(v is None for v in r.values()):
                raise ValueError('Malformed projection row')
            if r['season'] not in ('2023', '2024', '2025'):
                raise ValueError('Only unsealed 2023–25 seasons allowed')
            if not r['game_id'] or r['game_id'] in ids:
                raise ValueError('Missing/duplicate game identity')
            ids.add(r['game_id'])
            if any(r[k] not in ('True', 'False') for k in (*BASE, *COVERAGE)):
                raise ValueError('Availability fields must be booleans')
            rows.append({'season': int(r['season']), **{k: r[k] == 'True' for k in (*BASE, *COVERAGE)}})
    out = []
    for year in sorted({r['season'] for r in rows}):
        s = [r for r in rows if r['season'] == year]
        candidates = [r for r in s if r['fbs'] and not (r['indoor'] or r['venue_unknown'] or r['tbd'])]
        fbs = [r for r in s if r['fbs']]
        counts = Counter({k: sum(r[k] for r in s) for k in BASE})
        out.append(dict(year=year, all_schedule_games=len(s), fbs_games=len(fbs),
            indoor=counts['indoor'], unknown_roof=counts['roof_unknown'], open_retractable=counts['roof_open'],
            unknown_coordinates=counts['venue_unknown'], unknown_kickoff_or_tbd=counts['tbd'], neutral=counts['neutral'],
            fbs_indoor=sum(r['indoor'] for r in fbs), fbs_unknown_coordinates=sum(r['venue_unknown'] for r in fbs),
            fbs_unknown_kickoff_or_tbd=sum(r['tbd'] for r in fbs), fbs_neutral=sum(r['neutral'] for r in fbs),
            weather_candidates=len(candidates), no_station_map=sum(not r['venue_mapped'] for r in candidates),
            **{k: sum(r[k] for r in candidates) for k in COVERAGE}))
    return dict(rows=out, duplicate_game_ids=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projection', type=Path)
    args = parser.parse_args()
    print(json.dumps(aggregate(args.projection), indent=2, sort_keys=True))
