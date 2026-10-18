"""20 deterministic checks against running services; not an LLM correctness score."""
import json
import os
from statistics import mean
from time import perf_counter
import pandas as pd
import requests
from config import DATA, ROOT


def main():
    base = os.getenv('COPILOT_URL', 'http://127.0.0.1:8000')
    results = []
    def check(name, payload, predicate, status=200):
        before = perf_counter()
        try:
            response = requests.post(f'{base}/ask', json={'question': 'Show the relevant fault inspection procedure', **payload}, timeout=180)
            passed = response.status_code == status and predicate(response.json())
            detail = '' if passed else f'Unexpected response (HTTP {response.status_code})'
        except requests.RequestException:
            passed, detail = False, 'Service request failed'
        results.append({'case': name, 'passed': bool(passed), 'seconds': round(perf_counter()-before, 3), 'detail': detail})

    faults = [('BELT_SLIP','SOP001','M001'), ('SENSOR_FAULT','SOP002','M001'),
              ('SEAL_FAIL','SOP003','M002'), ('FILM_JAM','SOP004','M002'),
              ('PRESSURE_LOW','SOP005','M003'), ('TEMP_HIGH','SOP006','M003')]
    for fault, doc, mid in faults:
        check(f'retrieve_{fault}', {'intent': 'sop', 'machine_id': mid, 'fault_code': fault, 'question': fault + ' inspection procedure'},
              lambda r, doc=doc: any(x['document_id'] == doc for x in r['evidence']['sources']))

    # Independently aggregate the clean CSV, not the SQL function being evaluated.
    data = pd.read_csv(DATA / 'clean_downtime.csv')
    timestamps = pd.to_datetime(data.started_at, utc=True)
    for days in [3, 7]:
        mask = (timestamps >= '2026-10-01') & (timestamps < f'2026-10-{days+1:02}')
        for mid in ['M001','M002','M003']:
            expected = round(float(data.loc[mask & data.machine_id.eq(mid), 'duration_minutes'].sum()), 2)
            check(f'sql_{mid}_{days}days', {'intent': 'analytics', 'machine_id': mid, 'end_date': f'2026-10-{days:02}'},
                  lambda r, expected=expected: r['evidence']['downtime'][0]['downtime_minutes'] == expected)
    for mid in [None, 'M001', 'M002', 'M003']:
        check(f'combined_{mid}', {'intent': 'combined', 'machine_id': mid},
              lambda r: bool(r['evidence'].get('sources')) and bool(r['evidence'].get('inventory'))
              and all('stock_quantity' in p for p in r['evidence']['inventory']))
    check('invalid_date', {'start_date': '2026-10-08', 'end_date': '2026-10-01'}, lambda r: 'detail' in r, 422)
    check('invalid_machine', {'machine_id': 'M999'}, lambda r: 'detail' in r, 422)
    check('no_events', {'intent': 'combined', 'start_date': '2027-01-01', 'end_date': '2027-01-02'},
          lambda r: r['evidence']['sources'] == [] and r['evidence']['inventory'] == [])
    check('unknown_fault', {'intent': 'sop', 'fault_code': 'UNKNOWN_FAULT'}, lambda r: r['evidence']['sources'] == [])
    report = {'checks_passed': sum(r['passed'] for r in results), 'total': len(results),
              'mean_seconds': round(mean(r['seconds'] for r in results),3), 'results': results,
              'scope': 'Deterministic retrieval/SQL/integration checks. Generated answers require separate human review.'}
    (ROOT / 'evaluation_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    main()
