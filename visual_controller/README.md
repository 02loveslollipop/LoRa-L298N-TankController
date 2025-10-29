# Visual Controller Service

The visual controller provides a lightweight web UI and REST gateway for tank
operations. It writes control commands into Redis Streams for the
`control_broker` service to deliver to hardware, and streams live telemetry back
to browsers.

## Environment

- `REDIS_URL` (default `redis://localhost:6379/0`)
- `REDIS_COMMAND_STREAM` (default `tank_commands`)
- `REDIS_STATUS_STREAM` (default `tank_status`)
- `REDIS_COMMAND_MAXLEN` (default `500`)
- `REDIS_STATUS_STREAM_START` (default `0-0`)

## Endpoints

- `GET /health`
- `GET /tanks` – latest telemetry snapshot per tank
- `POST /command/{tank_id}` – enqueue command (JSON payload)
- `GET /controller/{tank_id}` – interactive browser UI
- `WS /ws/ui/{tank_id}` – telemetry updates for UI clients

## Running locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```
