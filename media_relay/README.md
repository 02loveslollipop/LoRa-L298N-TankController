# Media Relay Service

This folder contains the Mediamtx configuration and optional Docker bundle used for local testing of the low-latency relay (`rtsp.nene.02labs.me`). Production deployment is handled by the Terraform stack under `infra/terraform/media_relay`, which provisions an EC2 instance, installs Docker, copies `mediamtx.yml`, and runs the upstream `bluenviron/mediamtx` image behind an Elastic IP.

## Runtime configuration

The Terraform module renders credentials directly into `mediamtx.yml`. When running the container manually (outside of Terraform), you can still configure the following environment variables:

| Variable | Purpose |
| --- | --- |
| `RELAY_PUBLISH_USER` | Username the SBC uses while pushing the RTSP stream |
| `RELAY_PUBLISH_PASS` | Password the SBC uses while pushing the RTSP stream |
| `RELAY_VIEWER_USER` | Username required by frontend clients (set to `any` to allow anonymous access) |
| `RELAY_VIEWER_PASS` | Password required by frontend clients (leave blank when `RELAY_VIEWER_USER=any`) |

If you enable viewer authentication, update the frontend to use the same credentials when negotiating playback.

Ports exposed by the container:

- `8554/tcp`: RTSP ingest from the SBC
- `1935/tcp`: RTMP ingest (alternative to RTSP)
- `8888/tcp`: HTTP server (HLS playback and API)
- `8889/tcp` plus `8200/udp`: WebRTC signalling and media
- `9998/tcp`: Prometheus metrics (optional)
- `9999/tcp`: pprof endpoint (optional)

Ensure the EC2 security group created by Terraform allows inbound traffic on these ports (see `infra/terraform/media_relay`). Clients connect directly to the Elastic IP bound to the instance.

## Deployment bundle
The Dockerfile copies `mediamtx.yml` into an image and relies on the Mediamtx entrypoint to launch the server. Use it for local verification only; live infrastructure is managed via Terraform.
