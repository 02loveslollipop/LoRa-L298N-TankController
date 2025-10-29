# Stream Cleaner Service

This service trims Redis streams daily (default) so command and telemetry
messages older than 30 minutes are removed.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis/Valkey endpoint |
| `REDIS_COMMAND_STREAM` | `tank_commands` | Command stream name |
| `REDIS_STATUS_STREAM` | `tank_status` | Telemetry stream name |
| `STREAM_RETENTION_MINUTES` | `30` | Age threshold for trimming |
| `STREAM_CLEAN_INTERVAL_SECONDS` | `86400` | Interval between cleanups |

## Endpoints

- `GET /health`
- `POST /cleanup` – trigger cleanup manually

## Development

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```
