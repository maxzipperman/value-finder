# DRAFT props archive handoff and missing-stat clarification — October 2, 2026

NOT REGISTERED. Requires independent review and hub registration before outcome
joins. No primary threshold, direction, sport, market, season pool or decision
criterion is changed. Real CLI grading remains blocked in this repair.

## Purchased timing versus original registration

Section 2.4 originally chooses the last F3 snapshot at least five minutes before
kickoff. The legacy planner implements floor5(kickoff − 5 minutes). The actual
reviewed F3a acquisition instead purchased T24 and scheduled CLOSE_T10, using the
earlier independent/provider schedule restriction. Calling this T5 would be false.
The handoff retains CLOSE_T10; it does not re-plan or buy a replacement quote.

Proposed handoff: use the acquired T10 slot as a scheduled pregame close proxy,
subject to returned snapshot lag 0–600 seconds, market timestamp (fallback to book
only when absent) age 0–900 seconds at snapshot and 0–1500 at decision; both decision
and returned snapshot before all relevant schedule clocks; unresolved identity,
orientation or kickoff conflicts excluded. Returned close lead relative to provider
schedule must be 5–20 minutes. These are eligibility flags, not actual-first-play
certification. Event binding must have been observed by the decision. These bounds
are inherited from v4; they are not a claim that the original props registration
already approved them. Missing/unmatched opportunities stay in coverage tables.

## Book note pending timing adoption

The authorized completed 2025 archive contains 570 responses: 285 T24 and 285
CLOSE_T10. Read-only coverage found Pinnacle on 2670/3785 receiving-yard player-games
(70.54%) and 1291/1789 rushing-yard player-games (72.16%). These are offered-line
presence counts at any registered ten-book-panel member, by event ID and provider
player-name string, as section 2.4 defines. Paired-price or freshness failures do not
shrink that book-choice denominator; they are separate price eligibility exclusions.
A quote is not an outcome, and no outcome/roster selection was used for these counts.

Both fractions are below 80%, so the mechanical candidate is DraftKings. This is
T10 coverage, not evidence about unavailable T5 quotes. On registering this timing
amendment, the hub may activate the dated section 8 candidate note; until then the
existing parser does not recognize it as an active book selection. No selection on
2023–24 or on outcomes, and no later book fill-in, is introduced.

## Unknown statistics versus verified zeros

Section 2.7 says no attempt in a market is zero; it does not prove that every null
statistic means no attempt. Proposed clarification: only a known finite source
statistic (including explicit zero), or a separately validated no-attempt derivation,
may be graded. Unknown/null/nonfinite or conflicting player-game statistics are
excluded and counted. Exact duplicate source records are deduplicated; conflicting
records are not summed. Same-season descriptive medians use known finite statistics
and exclude conflicting source rows. This may change sample size and is declared
before outcomes, not silently called equivalent to the previous implementation.

The registered missing-player_week-row void proxy remains in the original NFL test;
it must not be generalized into book-specific settlement for new markets. Broad
settlement helpers require separately verified terms and participation. Kicking
points derives from known fg_made and pat_made, not the legacy derived column whose
builder fills null components with zero. No new actual outcome join is enabled.
