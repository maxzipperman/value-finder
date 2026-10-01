"""The grader for the registered props test (issue #10) on F3's cached event-odds answers.

  lines.py         F3's calls and rows (sealed calls never read), the book rule's coverage, the main line at the book
  stats.py         the power, additive and multiplicative de-vigs; the excess under rate, its two SEs, p, ROI
  roster.py        the committed season roster (config/props/nfl_rosters_2023_2025.csv) and the name -> player_id map
  outcomes.py      nflverse's schedule (kickoffs, no score) and player_week, both read for 2023-25 only
  grade.py         the join and every exclusion, the tables, the readout, the line move, the F3b gate, the decision
  registration.py  the count and the bar from STATUS.md and the registration's header; the section 8 book note
  fixture.py       a synthetic F3 fixture for tests and `--fixture`
  run.py           `uv run markets props-grade`

The rule, its exclusions and its decision criteria: nfl-weather/PREREGISTRATION_PROPS.md (registered September 30,
2026). The grader adds no variant: it implements the one already in the running count.
Paper only: nothing here places, sizes or routes a bet.
"""
