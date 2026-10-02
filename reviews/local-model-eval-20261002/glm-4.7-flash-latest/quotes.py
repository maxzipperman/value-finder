import datetime
import re

def select_quote(rows, decision, kickoff):
    """
    Selects the best quote from a list of rows based on specific eligibility criteria.

    Args:
        rows (list of dict): List of quote dictionaries. Expected keys:
                             'id', 'snapshot_utc', 'last_update_utc', 'price'.
        decision (datetime.datetime): The decision time (aware).
        kickoff (datetime.datetime): The kickoff time (aware).

    Returns:
        dict or None: The original dict of the eligible row with the latest snapshot,
                      or None if no row is eligible.
    """
    eligible_rows = []

    for row in rows:
        # Extract fields
        snapshot_str = row.get('snapshot_utc')
        last_update_str = row.get('last_update_utc')
        price_val = row.get('price')

        # --- 1. Clock Validation ---
        # Check if snapshot_utc is a string and parseable
        if not isinstance(snapshot_str, str):
            continue
        
        # Check if last_update_utc is a string and parseable
        if not isinstance(last_update_str, str):
            continue

        # Parse snapshot_utc
        try:
            snapshot_utc = datetime.datetime.fromisoformat(snapshot_str)
        except ValueError:
            continue

        # Parse last_update_utc
        try:
            last_update_utc = datetime.datetime.fromisoformat(last_update_str)
        except ValueError:
            continue

        # Check timezone awareness
        if snapshot_utc.tzinfo is None or last_update_utc.tzinfo is None:
            continue

        # --- 2. Time Validation ---
        # Check if clocks are at or before decision
        if snapshot_utc > decision or last_update_utc > decision:
            continue

        # Check if clocks are strictly before kickoff
        if snapshot_utc >= kickoff or last_update_utc >= kickoff:
            continue

        # --- 3. Price Validation ---
        # Check if price is numeric (int or float) and finite
        if isinstance(price_val, bool):
            continue
        
        try:
            price = float(price_val)
        except (ValueError, TypeError):
            continue

        if not (isinstance(price, (int, float)) and datetime.math.isfinite(price)):
            continue

        # Check American odds absolute value
        if abs(price) < 100:
            continue

        # --- 4. Ordering Validation ---
        # Check if last_update_utc is at or before snapshot_utc
        if last_update_utc > snapshot_utc:
            continue

        # --- 5. Selection ---
        # Add to eligible list
        eligible_rows.append(row)

    if not eligible_rows:
        return None

    # Sort eligible rows by snapshot_utc descending, then by id ascending
    # We use a key function to access the values safely
    def sort_key(row):
        return (-row['snapshot_utc'], row['id'])

    eligible_rows.sort(key=sort_key)

    # Return the first element (lexicographically smallest id for ties)
    return eligible_rows[0]
