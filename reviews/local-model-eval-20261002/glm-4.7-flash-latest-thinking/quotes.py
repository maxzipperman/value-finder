from datetime import datetime
import math

def select_quote(rows, decision, kickoff):
    """
    Selects the best quote from a list of rows based on specific eligibility criteria.
    
    Args:
        rows (list of dict): List of quote dictionaries.
        decision (datetime): The decision time (aware).
        kickoff (datetime): The kickoff time (aware).
        
    Returns:
        dict or None: The best eligible quote dict, or None if none found.
    """
    eligible = []

    for row in rows:
        # Check for required keys
        if not all(k in row for k in ('id', 'snapshot_utc', 'last_update_utc', 'price')):
            continue

        snapshot = row['snapshot_utc']
        last_update = row['last_update_utc']
        price = row['price']

        # 1. Clocks must be timezone-aware datetime objects
        if not (isinstance(snapshot, datetime) and snapshot.tzinfo is not None):
            continue
        if not (isinstance(last_update, datetime) and last_update.tzinfo is not None):
            continue

        # 2. Time constraints
        # Both clocks must be at or before decision
        if snapshot > decision or last_update > decision:
            continue
        # Both clocks must be strictly before kickoff
        if snapshot >= kickoff or last_update >= kickoff:
            continue

        # 3. Price validation
        is_numeric = False
        if isinstance(price, (int, float)):
            # Reject booleans explicitly (bool is subclass of int)
            if isinstance(price, bool):
                continue
            is_numeric = True
        elif isinstance(price, str):
            try:
                price_val = float(price)
                is_numeric = True
                price = price_val
            except ValueError:
                continue

        if not is_numeric:
            continue

        # Check finite and odds
        if not (isinstance(price, (int, float)) and math.isfinite(price)):
            continue
        if abs(price) < 100:
            continue

        # 4. Ordering constraint: last_update_utc must be at or before snapshot_utc
        if last_update > snapshot:
            continue

        eligible.append(row)

    if not eligible:
        return None

    # Sort by snapshot_utc descending, then id ascending
    # Using sorted to ensure we don't mutate the input list 'rows'
    best = sorted(eligible, key=lambda r: (-r['snapshot_utc'], r['id']))

    return best[0]
