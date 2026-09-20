# OpsRelay API

Base URL locally: `http://localhost:8080/api`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | health check |
| GET | `/dashboard` | complete operational dashboard |
| GET | `/orders` | order list |
| GET | `/orders/{id}` | order + risk + events + recommendations + actions |
| GET | `/machines` | machine state |
| GET | `/risk/{id}` | current or recalculated risk |
| GET | `/events` | recent events |
| POST | `/events` | ingest factory event |
| POST | `/risk/recalculate` | force risk recalculation |
| POST | `/agent/query` | grounded OpsRelay agent query |
| GET | `/recommendations` | recovery recommendations |
| POST | `/actions` | approve and execute recommendation |
| GET | `/actions` | executed actions |
| GET | `/audit` | audit trail |

## Example event

```json
{
  "orderId": "ORD-1048",
  "machineId": "CNC-04",
  "type": "MACHINE_STOP",
  "durationMinutes": 25,
  "description": "Coolant pressure low; machine stopped."
}
```
