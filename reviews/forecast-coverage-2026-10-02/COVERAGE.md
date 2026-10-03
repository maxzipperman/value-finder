# Outcome-blind forecast availability — October 2, 2026

This persists the previous local audit's **aggregate metadata evidence**, with
an independent recomputation from its private projected CSVs. It is not a new
raw MOS-cache scan, decision-vintage certification, executable-price join or
strategy result. No per-game inputs, forecast values, live-2026 metadata, raw
paths or operational digests are published. `aggregate-coverage.json` contains
all denominators; `projected_coverage.py` accepts only the exact boolean metadata
projection and seasons 2023–25, rejecting outcome/price columns and duplicates.
Private input projections remain local. Projection schema checking cannot prove
that an upstream availability calculation or supplied metadata is truthful.

## Denominators and measured feasibility

Candidates are FBS-involved (CFB), outdoor, with coordinates and known kickoff.
No price, score, completion or cancelled-game outcome filter is applied. Roof
flags are historical schedule metadata, not decision-time roof-status vintages.

| Sport / season | Schedule games | Weather candidates | No station map | Covering MOS T48 / T24 | Previous-day 1 / 2 / 3 wind |
|---|---:|---:|---:|---:|---:|
| NFL 2023 | 285 | 199 | 16 | 183 / 183 | 5 / 5 / 3 |
| NFL 2024 | 285 | 187 | 5 | 182 / 182 | 187 / 187 / 187 |
| NFL 2025 | 285 | 193 | 0 | 193 / 193 | 193 / 193 / 193 |
| CFB 2023 | 3,734 | 835 | 19 | 815 / 815 | 0 / 0 / 0 |
| CFB 2024 | 3,801 | 849 | 19 | 816 / 816 | 833 / 833 / 833 |
| CFB 2025 | 3,831 | 876 | 21 | 855 / 855 | 876 / 876 / 876 |

CFB schedule totals include non-FBS games; FBS-involved totals are 910/920/934.
NFL 2023's five day-1 winds are January 2024 postseason, not fall-2023 coverage.
Candidates with a station but no covering MOS include one CFB 2023 game and 14
CFB 2024 games; the map alone does not establish forecast availability.

The audit assumes MOS public availability at initialization **plus five hours**;
that is an assumption, not a verified historical publication timestamp. It uses
the existing station fallback within 40km, and requires the four-hour CFB wind
window versus kickoff wind for NFL. The covering-run fallback is feasibility,
not an adopted strategy. Exact T72 covering MOS is **0 in every season** under
that assumption and the short-range product's horizon. Calendar day-3 coverage
(NFL 93/99/104, CFB 1/0/0) does not establish elapsed T72 coverage.

At T10 minutes the latest run can fail to cover the target while an older run
covers it. Latest-only counts: NFL 181/180/192; CFB 741/734/766. Covering-run counts
remain 183/182/193 and 815/816/855. Choosing an older run or another station needs
prospective outcome-blind rules before any grading. Attach weather to the actual
price decision timestamp, never blindly equate previous-day1 with exact T24.

## Ranked sources to investigate, not a new download authorization

1. [IEM MOS archive](https://mesonet.agron.iastate.edu/mos/) and
   [pyIEM parser](https://github.com/akrherz/pyIEM/blob/main/src/pyiem/nws/products/mos.py):
   first use existing point-cache coverage; investigate longer-horizon MOS products
   separately for T72. Do not treat short-range MAV as sufficient.
2. [NOAA GFS archive](https://registry.opendata.aws/noaa-gfs-bdp-pds/) and
   [Herbie](https://github.com/blaylockbk/Herbie): candidate for earlier horizons;
   prefer indexed subsets to bulk whole-GRIB downloads; establish availability lag.
3. [NOAA HRRR archive](https://registry.opendata.aws/noaa-hrrr-pds/) and
   [HRRR product documentation](https://www.nco.ncep.noaa.gov/pmb/products/hrrr/):
   candidate for near-kickoff weather; verify each cycle's horizon and archive format.
4. [NOAA NBM archive](https://registry.opendata.aws/noaa-nbm/): candidate blend;
   a blend mean is not independent ensemble-member evidence.
5. [NCAR GDEX GFS dataset](https://gdex.ucar.edu/datasets/d084001/) and
   [GDEX client](https://github.com/NCAR/gdex-api-client): candidate alternative
   archive/subsetting route; validate issued forecasts separately from analyses.
6. [NCEI NDFD archive](https://www.ncei.noaa.gov/products/weather-climate-models/national-digital-forecast-database)
   and [grib2io](https://github.com/NOAA-MDL/grib2io): candidate human forecast-grid
   route; archive-prefix failures do not establish dataset absence.

[Open-Meteo previous runs](https://open-meteo.com/en/docs/previous-runs-api),
[historical forecasts](https://open-meteo.com/en/docs/historical-forecast-api), and
[single runs](https://open-meteo.com/en/docs/single-runs-api) are distinct products.
A fixed lead or stitched history is not proof of the precise issued run available
at a chosen decision clock; verify vintage and model selection. ERA5, analysis
fields and later hindcasts do not supply decision-time forecast evidence.

Future recommendation: immutable fetch envelopes recording model/run and actual
fetch/publication time, and an hourly/near-kickoff collector where the registered
question needs it. This PR changes no alert frequency, collector or job and makes
no new archive probe. Missing weather excludes only weather-dependent analysis;
it must not block independent props coverage or create a profitability gate for
otherwise authorized core acquisition.
