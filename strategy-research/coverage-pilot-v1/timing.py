"""Additional prospective clock veto; never substitutes for base eligibility."""
from datetime import datetime, timezone


def utc(value):
    if not isinstance(value, str):
        raise ValueError('missing clock')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def scheduled_guard(*, base_eligible, requested, returned, execution,
                    provider_kickoffs, independent_kickoffs):
    """Apply to both entry and close. execution is historical hypothetical fill
    time, NOT today's archive download timestamp. Require it explicitly; caller
    may bind it to requested time for a zero-delay quote-feasibility diagnostic.
    This veto cannot admit an otherwise ineligible row or certify actual play.
    All relevant scheduled clocks must be supplied by the authenticated adapter.
    """
    reasons = []
    if base_eligible is not True:
        reasons.append('base_ineligible')
    try:
        if not provider_kickoffs or not independent_kickoffs:
            raise ValueError('both schedule sources required')
        decisions = [utc(requested), utc(returned), utc(execution)]
        starts = [utc(v) for v in [*provider_kickoffs, *independent_kickoffs]]
        if decisions[1] > decisions[0]:
            reasons.append('snapshot_after_request')
        if decisions[2] < decisions[0]:
            reasons.append('execution_before_decision')
        if max(decisions) >= min(starts):
            reasons.append('decision_snapshot_or_execution_not_before_schedule')
    except (ValueError, TypeError, OverflowError):
        reasons.append('missing_or_invalid_clock')
    return {'eligible': not reasons, 'reasons': reasons,
            'timing_basis': 'scheduled_proxy', 'actual_play_certified': False}
