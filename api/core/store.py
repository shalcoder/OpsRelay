from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
except Exception:  # pragma: no cover
    boto3 = None
    Key = None
    Attr = None


class BaseStore:
    def list_orders(self) -> list[dict[str, Any]]: raise NotImplementedError
    def get_order(self, order_id: str) -> dict[str, Any] | None: raise NotImplementedError
    def put_order(self, order: dict[str, Any]) -> None: raise NotImplementedError
    def update_order(self, order_id: str, patch: dict[str, Any]) -> dict[str, Any]: raise NotImplementedError
    def list_machines(self) -> list[dict[str, Any]]: raise NotImplementedError
    def put_machine(self, machine: dict[str, Any]) -> None: raise NotImplementedError
    def update_machine(self, machine_id: str, patch: dict[str, Any]) -> dict[str, Any]: raise NotImplementedError
    def add_event(self, event: dict[str, Any]) -> None: raise NotImplementedError
    def list_events(self, order_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]: raise NotImplementedError
    def put_risk(self, risk: dict[str, Any]) -> None: raise NotImplementedError
    def get_risk(self, order_id: str) -> dict[str, Any] | None: raise NotImplementedError
    def put_recommendation(self, rec: dict[str, Any]) -> None: raise NotImplementedError
    def list_recommendations(self, order_id: str | None = None) -> list[dict[str, Any]]: raise NotImplementedError
    def put_action(self, action: dict[str, Any]) -> None: raise NotImplementedError
    def list_actions(self, order_id: str | None = None) -> list[dict[str, Any]]: raise NotImplementedError
    def add_audit(self, entry: dict[str, Any]) -> None: raise NotImplementedError
    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]: raise NotImplementedError
    def add_agent_session(self, session: dict[str, Any]) -> None: raise NotImplementedError
    def list_agent_sessions(self, order_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]: raise NotImplementedError


class JsonStore(BaseStore):
    def __init__(self, path: str = "data/local_store.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        if not self.path.exists():
            self._write({"orders": [], "machines": [], "events": [], "risks": [], "recommendations": [], "actions": [], "audit": [], "agent_sessions": []})
        self.data = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"orders": [], "machines": [], "events": [], "risks": [], "recommendations": [], "actions": [], "audit": []}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _save(self) -> None:
        self._write(self.data)

    def list_orders(self): return copy.deepcopy(self.data["orders"])
    def get_order(self, order_id): return next((copy.deepcopy(x) for x in self.data["orders"] if x["id"] == order_id), None)
    def put_order(self, order):
        with self.lock:
            self.data["orders"] = [x for x in self.data["orders"] if x["id"] != order["id"]] + [copy.deepcopy(order)]; self._save()
    def update_order(self, order_id, patch):
        with self.lock:
            item = self.get_order(order_id)
            if not item: raise KeyError(order_id)
            item.update(copy.deepcopy(patch)); item["updatedAt"] = datetime.now(timezone.utc).isoformat(); self.put_order(item); return item
    def list_machines(self): return copy.deepcopy(self.data["machines"])
    def put_machine(self, machine):
        with self.lock:
            self.data["machines"] = [x for x in self.data["machines"] if x["id"] != machine["id"]] + [copy.deepcopy(machine)]; self._save()
    def update_machine(self, machine_id, patch):
        with self.lock:
            item = next((copy.deepcopy(x) for x in self.data["machines"] if x["id"] == machine_id), None)
            if not item: raise KeyError(machine_id)
            item.update(copy.deepcopy(patch)); self.put_machine(item); return item
    def add_event(self, event):
        with self.lock: self.data["events"].append(copy.deepcopy(event)); self._save()
    def list_events(self, order_id=None, limit=100):
        rows = [x for x in self.data["events"] if order_id is None or x.get("orderId") == order_id]
        return sorted(copy.deepcopy(rows), key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
    def put_risk(self, risk):
        with self.lock: self.data["risks"] = [x for x in self.data["risks"] if x["orderId"] != risk["orderId"]] + [copy.deepcopy(risk)]; self._save()
    def get_risk(self, order_id): return next((copy.deepcopy(x) for x in self.data["risks"] if x["orderId"] == order_id), None)
    def put_recommendation(self, rec):
        with self.lock:
            self.data["recommendations"] = [x for x in self.data["recommendations"] if x["id"] != rec["id"]] + [copy.deepcopy(rec)]; self._save()
    def list_recommendations(self, order_id=None): return [copy.deepcopy(x) for x in self.data["recommendations"] if order_id is None or x.get("orderId") == order_id]
    def put_action(self, action):
        with self.lock:
            self.data["actions"] = [x for x in self.data["actions"] if x["id"] != action["id"]] + [copy.deepcopy(action)]; self._save()
    def list_actions(self, order_id=None): return [copy.deepcopy(x) for x in self.data["actions"] if order_id is None or x.get("orderId") == order_id]
    def add_audit(self, entry):
        with self.lock: self.data["audit"].append(copy.deepcopy(entry)); self._save()
    def list_audit(self, limit=100): return list(reversed(copy.deepcopy(self.data["audit"][-limit:])))
    def add_agent_session(self, session):
        with self.lock:
            if "agent_sessions" not in self.data:
                self.data["agent_sessions"] = []
            self.data["agent_sessions"].append(copy.deepcopy(session))
            self._save()
    def list_agent_sessions(self, order_id=None, limit=50):
        with self.lock:
            sessions = self.data.get("agent_sessions", [])
            rows = [x for x in sessions if order_id is None or x.get("orderId") == order_id]
            return sorted(copy.deepcopy(rows), key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]


from decimal import Decimal


def _to_dynamo(val: Any) -> Any:
    return json.loads(json.dumps(val, default=str), parse_float=Decimal)


def _from_dynamo(val: Any) -> Any:
    if isinstance(val, list):
        return [_from_dynamo(x) for x in val]
    if isinstance(val, dict):
        return {k: _from_dynamo(v) for k, v in val.items()}
    if isinstance(val, Decimal):
        return int(val) if val % 1 == 0 else float(val)
    return val


class DynamoStore(BaseStore):
    def __init__(self) -> None:
        if not boto3: raise RuntimeError("boto3 is required for cloud mode")
        table_name = os.environ.get("OPSRELAY_TABLE_NAME", "opsrelay-main")
        self.table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ap-south-1")).Table(table_name)

    def _put(self, item: dict[str, Any]) -> None:
        self.table.put_item(Item=_to_dynamo(item))

    def _query(self, pk: str) -> list[dict[str, Any]]:
        response = self.table.query(KeyConditionExpression=Key("pk").eq(pk))
        return _from_dynamo(response.get("Items", []))

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"pk": pk, "sk": sk}).get("Item")
        return _from_dynamo(item) if item else None

    def list_orders(self): return [x["data"] for x in self._query("ORDERS")]
    def get_order(self, order_id):
        item = self._get(f"ORDER#{order_id}", "META")
        return item["data"] if item else None
    def put_order(self, order):
        item={"pk":"ORDERS","sk":order["id"],"entity":"ORDER","data":order}
        self._put(item)
        self._put({"pk": f"ORDER#{order['id']}", "sk": "META", "entity": "ORDER", "data": order})
    def update_order(self, order_id, patch):
        x = self.get_order(order_id)
        if not x: raise KeyError(order_id)
        x.update(patch); x["updatedAt"] = datetime.now(timezone.utc).isoformat(); self.put_order(x); return x
    def list_machines(self): return [x["data"] for x in self._query("MACHINES")]
    def put_machine(self, machine):
        self._put({"pk":"MACHINES","sk":machine["id"],"entity":"MACHINE","data":machine})
        self._put({"pk": f"MACHINE#{machine['id']}", "sk": "META", "entity": "MACHINE", "data": machine})
    def update_machine(self, machine_id, patch):
        x = next((m for m in self.list_machines() if m["id"] == machine_id), None)
        if not x: raise KeyError(machine_id)
        x.update(patch); self.put_machine(x); return x
    def add_event(self, event): self._put({"pk": f"ORDER#{event.get('orderId','UNASSIGNED')}", "sk": f"EVENT#{event['timestamp']}#{event['id']}", "entity": "EVENT", "data": event})
    def list_events(self, order_id=None, limit=100):
        if order_id: items = self._query(f"ORDER#{order_id}")
        else:
            items = []
            for o in self.list_orders(): items.extend(self._query(f"ORDER#{o['id']}"))
        return [x["data"] for x in sorted(items, key=lambda y: y["sk"], reverse=True) if x.get("entity") == "EVENT"][:limit]
    def put_risk(self, risk): self._put({"pk": f"ORDER#{risk['orderId']}", "sk": "RISK", "entity": "RISK", "data": risk})
    def get_risk(self, order_id):
        x = self._get(f"ORDER#{order_id}", "RISK"); return x["data"] if x else None
    def put_recommendation(self, rec): self._put({"pk": f"ORDER#{rec['orderId']}", "sk": f"REC#{rec['id']}", "entity": "RECOMMENDATION", "data": rec})
    def list_recommendations(self, order_id=None):
        items = self._query(f"ORDER#{order_id}") if order_id else _from_dynamo(self.table.scan(FilterExpression=Attr("entity").eq("RECOMMENDATION")).get("Items", []))
        return [x["data"] for x in items if x.get("entity") == "RECOMMENDATION"]
    def put_action(self, action): self._put({"pk": f"ORDER#{action['orderId']}", "sk": f"ACTION#{action['id']}", "entity": "ACTION", "data": action})
    def list_actions(self, order_id=None):
        items = self._query(f"ORDER#{order_id}") if order_id else _from_dynamo(self.table.scan(FilterExpression=Attr("entity").eq("ACTION")).get("Items", []))
        return [x["data"] for x in items if x.get("entity") == "ACTION"]
    def add_audit(self, entry): self._put({"pk": "AUDIT", "sk": f"{entry['timestamp']}#{entry['id']}", "entity": "AUDIT", "data": entry})
    def list_audit(self, limit=100): return [x["data"] for x in sorted(self._query("AUDIT"), key=lambda y: y["sk"], reverse=True)[:limit]]
    def add_agent_session(self, session): self._put({"pk": f"SESSION#{session.get('orderId', 'GENERAL')}", "sk": f"{session['timestamp']}#{session['id']}", "entity": "AGENT_SESSION", "data": session})
    def list_agent_sessions(self, order_id=None, limit=50):
        pk = f"SESSION#{order_id}" if order_id else "SESSION#GENERAL"
        return [x["data"] for x in sorted(self._query(pk), key=lambda y: y["sk"], reverse=True)[:limit]]


def make_store() -> BaseStore:
    if os.getenv("OPSRELAY_MODE", "local").lower() == "cloud" and boto3:
        return DynamoStore()
    return JsonStore(os.getenv("OPSRELAY_LOCAL_STORE", "data/local_store.json"))
