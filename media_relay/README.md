# Media Relay Service

This folder contains the container bundle deployed to the dedicated Elastic Beanstalk environment that serves as the low-latency relay (`rtsp.nene.02labs.me`). The container ships [Mediamtx](https://github.com/bluenviron/mediamtx), providing RTSP ingest together with WebRTC and LL-HLS playback for the robot camera stream.

## Runtime configuration

The container reads the following environment variables that must be configured in the Elastic Beanstalk environment before deploying:

| Variable | Purpose |
| --- | --- |
| `RELAY_PUBLISH_USER` | Username the SBC uses while pushing the RTSP stream |
| `RELAY_PUBLISH_PASS` | Password the SBC uses while pushing the RTSP stream |
| `RELAY_VIEWER_USER` | Optional username required by frontend clients (leave empty to disable auth) |
| `RELAY_VIEWER_PASS` | Optional password required by frontend clients (leave empty to disable auth) |

If you enable viewer authentication, update the frontend to use the same credentials when negotiating playback.

Ports exposed by the container:

- `8554/tcp`: RTSP ingest from the SBC
- `1935/tcp`: RTMP ingest (alternative to RTSP)
- `8888/tcp`: HTTP server (HLS playback and API)
- `8889/tcp` plus `UDP 8200-8299`: WebRTC signalling and media
- `9998/tcp`: Prometheus metrics (optional)
- `9999/tcp`: pprof endpoint (optional)

Ensure the Elastic Beanstalk load balancer and security groups forward the required ports. For WebRTC, terminate TLS at the load balancer and forward HTTPS traffic to port `8889`.

## Deployment bundle

The GitHub Actions workflow zips the contents of this folder and uploads the archive as an application version. The Dockerfile simply copies the Mediamtx configuration and launches the server binary.
