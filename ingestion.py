"""Pandas ETL: reject invalid events instead of inventing durations."""
import json
import sqlite3
import pandas as pd
from config import DATA, DB


def clean_events(raw, valid_machine_ids):
    df = raw.copy()
    df['machine_id'] = df['machine_id'].astype('string').str.strip().str.upper()
    for col in ['started_at', 'ended_at']:
        df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
    df['duration_minutes'] = (df['ended_at'] - df['started_at']).dt.total_seconds() / 60
    reasons = pd.Series('', index=df.index)
    checks = [
        (df['event_id'].isna() | df['event_id'].astype('string').str.strip().eq(''), 'missing event ID'),
        (df['event_id'].duplicated(), 'duplicate event ID'),
        (~df['machine_id'].isin(valid_machine_ids), 'unknown machine'),
        (df['started_at'].isna() | df['ended_at'].isna(), 'invalid timestamp'),
        (df['duration_minutes'] < 0, 'negative duration'),
        (df['fault_code'].isna(), 'missing fault code'),
    ]
    for mask, label in checks:
        reasons.loc[mask.fillna(True) & reasons.eq('')] = label
    df['rejection_reason'] = reasons
    clean = df.loc[reasons.eq('')].drop(columns='rejection_reason').copy()
    rejected = df.loc[reasons.ne('')].copy()
    for col in ['started_at', 'ended_at']:
        clean[col] = clean[col].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return clean, rejected


def main():
    machines = pd.read_csv(DATA / 'machines.csv')
    clean, rejected = clean_events(pd.read_csv(DATA / 'downtime.csv'), set(machines.machine_id))
    with sqlite3.connect(DB) as con:
        machines.to_sql('machines', con, if_exists='replace', index=False)
        clean.to_sql('downtime_events', con, if_exists='replace', index=False)
        con.execute('CREATE INDEX IF NOT EXISTS idx_event_machine ON downtime_events(machine_id, started_at)')
    clean.to_csv(DATA / 'clean_downtime.csv', index=False)
    rejected.to_csv(DATA / 'rejected_downtime.csv', index=False)
    report = {'raw': len(clean) + len(rejected), 'accepted': len(clean), 'rejected': len(rejected)}
    (DATA / 'cleaning_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()