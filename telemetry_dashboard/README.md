# Telemetry Dashboard

This Dash + Plotly application renders real-time telemetry from the tank fleet. It subscribes to the Redis `tank_status` stream (via the control broker) and visualizes:

- Environment readings (temperature/humidity)
- GPS trail and speed
- Basic connection metadata (satellites, HDOP, timestamps)

## Configuration

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Connection string for the telemetry Redis instance |
| `REDIS_STATUS_STREAM` | `tank_status` | Redis stream containing incoming telemetry payloads |
| `HISTORY_LIMIT` | `500` | Maximum number of samples kept in memory per process |
| `REFRESH_INTERVAL_MS` | `3000` | Polling interval for the Dash client |

## Development

```bash
cd telemetry_dashboard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Visit http://127.0.0.1:8050/ to view the dashboard.

## Deployment

Deploy like the other Elastic Beanstalk services:

```bash
zip -r telemetry-dashboard.zip .
aws elasticbeanstalk create-application-version ... # etc.
```

The provided `Dockerfile` and `Procfile` mirror the other services in this repository for compatibility with the existing pipeline.
