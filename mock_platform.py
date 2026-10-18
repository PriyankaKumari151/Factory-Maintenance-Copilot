"""Local simulated enterprise API. Not a Poka/Weaver integration."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from config import DATA

app = FastAPI(title='Synthetic factory platform')


class Ticket(BaseModel):
    machine_id: str = Field(pattern=r'^M00[1-3]$')
    fault_code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=10, max_length=2000)


@app.get('/parts/{part_id}')
def get_part(part_id: str):
    parts = json.loads((DATA / 'inventory.json').read_text(encoding='utf-8'))
    found = next((p for p in parts if p['part_id'] == part_id), None)
    if found is None:
        raise HTTPException(404, 'Unknown part')
    return found


@app.post('/tickets')
def create_ticket(ticket: Ticket, idempotency_key: Annotated[str, Header(min_length=1, max_length=100)]):
    payload = json.dumps(ticket.model_dump(), sort_keys=True)
    with sqlite3.connect(DATA / 'platform.db') as con:
        con.execute('''CREATE TABLE IF NOT EXISTS tickets (
            request_key TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT NOT NULL)''')
        # Serialise check+insert for concurrent requests with the same key.
        con.execute('BEGIN IMMEDIATE')
        existing = con.execute('SELECT payload,result FROM tickets WHERE request_key=?', (idempotency_key,)).fetchone()
        if existing:
            if existing[0] != payload:
                raise HTTPException(409, 'Idempotency key reused with different content')
            return json.loads(existing[1])
        result = {**ticket.model_dump(), 'ticket_id': str(uuid4()), 'status': 'open',
                  'created_at': datetime.now(timezone.utc).isoformat()}
        con.execute('INSERT INTO tickets VALUES (?,?,?)', (idempotency_key, payload, json.dumps(result)))
        return result
