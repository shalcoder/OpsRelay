from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'api'))
from core.store import JsonStore

data=json.loads((ROOT/'data'/'demo.json').read_text())
store=JsonStore(str(ROOT/'data'/'local_store.json'))
store.data={"orders":[],"machines":[],"events":[],"risks":[],"recommendations":[],"actions":[],"audit":[]}
for x in data['orders']: store.put_order(x)
for x in data['machines']: store.put_machine(x)
for x in data['events']: store.add_event(x)
print(f"Seeded {len(data['orders'])} orders, {len(data['machines'])} machines, {len(data['events'])} events")
