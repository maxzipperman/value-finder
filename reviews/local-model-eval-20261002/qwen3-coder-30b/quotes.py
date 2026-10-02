import datetime
import re
import math

def select_quote(rows, decision, kickoff):
    if not rows:
        return None
    
    # Validate decision and kickoff are timezone-aware
    if decision.tzinfo is None:
        return None
    if kickoff.tzinfo is None:
        return None
    
    eligible_rows = []
    
    for row in rows:
        # Check required keys
        if not all(k in row for k in ['id', 'snapshot_utc', 'last_update_utc', 'price']):
            continue
            
        # Parse timestamps
        try:
            snapshot = datetime.datetime.fromisoformat(row['snapshot_utc'].replace('Z', '+00:00'))
            last_update = datetime.datetime.fromisoformat(row['last_update_utc'].replace('Z', '+00:00'))
        except (ValueError, TypeError):
            continue
            
        # Validate timezone awareness
        if snapshot.tzinfo is None or last_update.tzinfo is None:
            continue
            
        # Check if clocks are at or before decision
        if snapshot > decision or last_update > decision:
            continue
            
        # Check if clocks are strictly before kickoff
        if snapshot >= kickoff or last_update >= kickoff:
            continue
            
        # Check if last_update is at or before snapshot
        if last_update > snapshot:
            continue
            
        # Validate price
        price = row['price']
        if isinstance(price, bool):
            continue
        if isinstance(price, (int, float)):
            if not math.isfinite(price):
                continue
            price_value = float(price)
        elif isinstance(price, str):
            try:
                price_value = float(price)
                if not math.isfinite(price_value):
                    continue
            except ValueError:
                continue
        else:
            continue
            
        # Check absolute value of odds
        if abs(price_value) < 100:
            continue
            
        eligible_rows.append({
            'row': row,
            'snapshot': snapshot,
            'id': row['id']
        })
    
    if not eligible_rows:
        return None
    
    # Sort by snapshot time (descending) and then by id (ascending)
    eligible_rows.sort(key=lambda x: (-x['snapshot'].timestamp(), x['id']))
    
    # Find the latest snapshot
    max_snapshot = eligible_rows[0]['snapshot']
    latest_rows = [r for r in eligible_rows if r['snapshot'] == max_snapshot]
    
    # Among latest, choose lexicographically smallest id
    latest_rows.sort(key=lambda x: x['id'])
    
    return latest_rows[0]['row']
