"""Read-only operational queries. Date windows use event START time, UTC, inclusive dates."""
import sqlite3
from datetime import date, timedelta
from config import DB


def query(sql, params=()):
    with sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(sql, params)]


def window(start_date, end_date):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start:
        raise ValueError('End date must be on or after start date.')
    return start.isoformat() + 'T00:00:00Z', (end + timedelta(days=1)).isoformat() + 'T00:00:00Z'


def machines():
    return query('SELECT * FROM machines ORDER BY machine_id')


def downtime_summary(start_date, end_date, machine_id=None):
    start, end = window(start_date, end_date)
    return query('''SELECT m.machine_id, m.machine_name, m.machine_type,
          ROUND(SUM(e.duration_minutes), 2) AS downtime_minutes, COUNT(*) AS event_count
        FROM downtime_events e JOIN machines m ON e.machine_id = m.machine_id
        WHERE e.started_at >= ? AND e.started_at < ? AND (? IS NULL OR m.machine_id = ?)
        GROUP BY m.machine_id, m.machine_name, m.machine_type
        ORDER BY downtime_minutes DESC, m.machine_id''', (start, end, machine_id, machine_id))


def fault_summary(machine_id, start_date, end_date):
    start, end = window(start_date, end_date)
    return query('''SELECT fault_code, COUNT(*) AS event_count,
        ROUND(SUM(duration_minutes), 2) AS downtime_minutes FROM downtime_events
        WHERE machine_id = ? AND started_at >= ? AND started_at < ?
        GROUP BY fault_code ORDER BY downtime_minutes DESC, fault_code''', (machine_id, start, end))
