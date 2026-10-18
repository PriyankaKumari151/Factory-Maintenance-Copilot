"""Generate reproducible SYNTHETIC factory records; never deletes ticket data."""
import json
import random
from datetime import datetime, timedelta
import pandas as pd
from config import DATA


def main():
    DATA.mkdir(exist_ok=True)
    rng = random.Random(42)
    machines = [    
        {'machine_id': 'M001', 'machine_name': 'Conveyor', 'machine_type': 'conveyor'},
        {'machine_id': 'M002', 'machine_name': 'Packaging machine', 'machine_type': 'packager'},
        {'machine_id': 'M003', 'machine_name': 'Compressor', 'machine_type': 'compressor'},
    ]
    pd.DataFrame(machines).to_csv(DATA / 'machines.csv', index=False)
    faults = {'M001': ['BELT_SLIP', 'SENSOR_FAULT'], 'M002': ['SEAL_FAIL', 'FILM_JAM'],
              'M003': ['PRESSURE_LOW', 'TEMP_HIGH']}
    rows = []
    for i in range(90):
        machine_id = machines[i % 3]['machine_id']
        start = datetime(2026, 10, 1) + timedelta(days=i % 10, hours=i % 8)
        duration = rng.randint(10, 40) + (45 if machine_id == 'M002' else 0)
        rows.append({'event_id': f'E{i:03}', 'machine_id': machine_id.lower() if i % 7 == 0 else machine_id,
                     'started_at': start.isoformat(), 'ended_at': (start + timedelta(minutes=duration)).isoformat(),
                     'fault_code': faults[machine_id][(i // 3) % 2]})
    rows += [rows[0].copy(), dict(rows[1], event_id='BAD_MISSING', ended_at=''),  ##bad data added for data cleaning exercise
             dict(rows[2], event_id='BAD_NEGATIVE', ended_at='2026-09-01T00:00:00')]
    pd.DataFrame(rows).to_csv(DATA / 'downtime.csv', index=False)
    inventory = [
        {'part_id': 'P001', 'part_name': 'Conveyor belt', 'stock_quantity': 3},
        {'part_id': 'P002', 'part_name': 'Photoelectric sensor', 'stock_quantity': 2},
        {'part_id': 'P003', 'part_name': 'Sealing element', 'stock_quantity': 0},
        {'part_id': 'P004', 'part_name': 'Film guide', 'stock_quantity': 4},
        {'part_id': 'P005', 'part_name': 'Pressure regulator', 'stock_quantity': 1},
        {'part_id': 'P006', 'part_name': 'Cooling filter', 'stock_quantity': 5},
    ]
    (DATA / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8') ##converts the inventory list into JSON
    print('Created 3 machines, 93 raw rows, and 6 parts. All data is synthetic.')


if __name__ == '__main__':
    main()
