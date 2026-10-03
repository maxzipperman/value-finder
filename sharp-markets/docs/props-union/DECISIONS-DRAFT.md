# NFL props union decisions — DRAFT October 3, 2026

NOT REGISTERED / NOT ADOPTED. This PR enables authenticated quote eligibility only.
It does not authorize any outcome join, scoring, global-count change or book note.
Existing [timing/stat draft](../props-archive/AMENDMENT-DRAFT.md) remains draft.

## Timing and missing-stat decisions

Extend that draft's acquired CLOSE_T10 interpretation explicitly to all three
NFL seasons,2023–25. Original section2.4 is floor5(kickoff−5min); no purchased T5
quote is invented, replaced or bought. Fixed acquired T24/CLOSE_T10 opportunities
are retained, including unresolved provider-only identities and missing responses.
Use the authenticated as-of event binding; independent, provider and response
schedule clocks must agree within five minutes and decision/snapshot must precede
all. Returned close lead5–20min; snapshot lag0–600sec, quote age0–900sec at snapshot
and0–1500sec at decision. T24 horizon remains the frozen classifier's24h−5min to
24h+10min. These are scheduled proxies, never verified first play or fills.

Unknown/null/nonfinite/conflicting statistics remain excluded and counted. Known
finite values including explicit zero are eligible only after identity/participation
and book terms are verified. No-attempt zero needs a separate validated derivation;
no weekly row is not a general book-specific void. Do not change the historical
missing-row proxy by silently calling this equivalent. Commit a dated amendment
before the first affected outcome join; report changed samples explicitly.

Candidate DraftKings derives solely from the existing2025 offered-line book test:
Pinnacle2670/3785 receiving and1291/1789 rushing, each below80%. Keep that candidate
conditional until timing/stat/count adoption and the dated section8 book note.
Never reselect it from2023/24, outcomes, fresher-pair coverage or a favorable result.
No other book fills gaps. Parser's current book remains inactive in this PR.

## Finite pooled discovery proposal

The machine-readable [discovery matrix](discovery-matrix.json) has **8 proposed
new deciding cells**: NFL × {rushing,receiving yards} × {actually offered Over,
actually offered Under} × {T24,CLOSE_T10} × one candidate book × one fixed all-player
main-line selection and power de-vig specification. Pool2023–25, with descriptive
year/market/missingness breakouts. This is retrospective discovery, not untouched
validation. 2026 stays sealed; a future forward confirmation needs its own protocol.

Each cell evaluates positive offered-side hit-rate excess against power-de-vig fair
probability; report actual-side unit-stake ROI, pushes/voids/unknowns separately.
Game/day dependence must enter inference; books/times/sides/lines from the same
player/game/market are not independent trials. Exact inference implementation and
adoption remain pending; no result code runs here. No stake optimization, thresholds,
model search, subset winners, weather or role selector is added to this matrix.

Use original main-line policy: both sides at the same book/label/point; every listed
line usable; choose power under-probability closest to0.5; equal distance within
1e−9 excludes; malformed or conflicting lines exclude, never pick after outcomes.
Reader reports quote pairs but deliberately does not call this main-line selection
or decision eligibility. Main-line/roster/participation/terms remain separate holds.

Original already-counted **one pooled receiving/rushing-under test** is a distinct
registered claim, not eight original tests. Its controls/readouts stay nondeciding.
The8 new market/side/time claims overlap some original exposures but create new
selection opportunities and count separately. Do not add the original1 twice.
Any additional threshold, model, subset, book/time selector or deciding sensitivity
must be logged, expand the finite matrix and invalidate its previously proposed K.

## Dated accounting reconciliation proposal

Worker review inspected main11474c6 and PR96 head08aec17094989894bb1d81e041b5065e240cd160.
271 is dated price-engine lineage233+38; preserve that frozen history. Main294 is
288+6 forecast/style specs. PR96 records20 NEW +6 REUSED models,26 unique model IDs
and23 contrasts. The20 new are8 NFL revision +8 CFB revision +4 NFL style. Completed
trials count even while publication is unmerged; reused6, contrasts23 and models26
are not additional increments. Thus supported historical search floor is314=294+20,
plus any intervening studies, not an adopted current count. Original props1 and
engine38 are already accounted for. No numeric global count is changed by this PR.

Before outcome access: hub resolves the intervening-trial ledger and original
frozen threshold applicability, adopts a dated reconciled baseline B, declares K=8
(or explicitly records changed cells), then fills the exact count/bar header for
this discovery as0.05/(B+K). The original props header/bar is a separate dated decision
preserving its lineage; do not silently choose271,294,314 or a new family/FDR rule.
No original engine verdict is recomputed by this draft.

Source lineage: [main STATUS](https://github.com/maxzipperman/value-finder/blob/11474c60567878d0fa5c7a14dceec982eb646980/STATUS.md),
[original props accounting](../../../../nfl-weather/PREREGISTRATION_PROPS.md#4-variants-and-the-bar),
[PR96 trial ledger](https://github.com/maxzipperman/value-finder/blob/08aec17094989894bb1d81e041b5065e240cd160/strategy-research/expanded_lab/registration_evidence/trial_ledger.json),
[PR96 completed manifest](https://github.com/maxzipperman/value-finder/blob/08aec17094989894bb1d81e041b5065e240cd160/strategy-research/expanded_lab/registration_evidence/manifest.json).
Independent worker checklist: project research-lab/reviews/variant-lineage-and-role-readiness-review.md.

The season-wide QB membership helper can change earlier RB1 labels when a later
game is appended. Its traced historical descriptive consumers do not establish a
current all-player primary-grader dependency. This reader imports neither helper
nor role tables. Any future RB cohort must use a separately reviewed prefix-invariant
policy; no helper fix or historical rerun is bundled here.
