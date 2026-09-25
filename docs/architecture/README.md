# Architecture diagrams

The [end-to-end diagram](rendered/system-architecture.svg) is the best overview for a general audience. It separates browser commands and gateway status from the independent camera/video route. The [AWS deployment diagram](rendered/aws-deployment.svg) uses AWS service icons and nested resource boundaries; solid links show runtime traffic and dashed links show deployment. Both are 16:9 SVGs with 2880×1620 PNG exports.

![End-to-end teleoperation architecture](rendered/system-architecture.svg)

| Artifact | Purpose | Editable source |
| --- | --- | --- |
| [End-to-end architecture](rendered/system-architecture.svg) ([PNG](rendered/system-architecture.png)) | Primary project overview and general-audience image | [system-architecture.py](system-architecture.py) |
| [AWS deployment](rendered/aws-deployment.svg) ([PNG](rendered/aws-deployment.png)) | Elastic Beanstalk, Valkey, EC2 relay, S3, and delivery workflows | [aws-deployment.py](aws-deployment.py) |
| [Forward-command sequence](command-sequence.mmd) | Compact code-oriented command and gateway-status timeline | [command-sequence.mmd](command-sequence.mmd) |

## Verified paths

**Command:** Browser `POST /command/{tank_id}` → Visual Controller → Redis `tank_commands` → Control Broker → gateway WebSocket client → encrypted LoRa frame → robot ESP32 receiver → L298N → left/right motors. The gateway is a separate LilyGO T-Beam/ESP32 device; the robot receiver does not connect to the broker by WebSocket.

**Status:** The gateway sends heartbeat/state reports over its WebSocket connection. The broker writes them to `tank_status`; the Visual Controller reads that stream and pushes updates to browser UI WebSocket clients. The receiver firmware has no LoRa return path, so this is gateway-reported state, **not a robot acknowledgement**. The gateway currently constructs a `ws://` connection; the diagrams say “WebSocket” without asserting TLS for that hop.

**Video:** USB camera → Radxa Rock 3C → FFmpeg H.264 → RTSP uplink → MediaMTX on EC2 → browser WebRTC/WHEP player. Rockchip hardware encoding is available, while the build script also supports a CPU variant; the diagram names the codec without assuming a particular deployed build. MediaMTX enables HLS as another output, but the repository's browser player uses WHEP. The browser initiates WHEP HTTP signaling; the media arrow shows the video returned to it. The diagrams describe the intended protocol path; the repository does not contain an end-to-end browser playback test. Verify `VITE_WHEP_URL` against the relay's `robot` path when deploying.

**LoRa:** The shared protocol implements a 16-byte AES-256-CBC control frame with CRC32 and duplicate-sequence checking. “Field-tested ~1.5 km” records the project field test supplied for this documentation; the distance is not measured by source code.

The separate radar source can send radar, GPS, and environmental readings through the broker and `tank_radar` stream. Those optional telemetry features are outside the core teleoperation diagram.

## AWS deployment scope

Pushes to `main` package the Control Broker, Visual Controller, Stream Cleaner, and Telemetry Dashboard, upload bundles to S3, then update their Elastic Beanstalk application versions/environments. A manual GitHub Actions dispatch runs Terraform for the EC2 media relay, its Security Group, and a new or reused Elastic IP. EC2 user data runs the upstream MediaMTX Docker image; the `media_relay/` Docker bundle is for local testing. Caddy/TLS is conditional on a media domain setting; when enabled, it proxies WHEP and HLS HTTP endpoints. The repository's Terraform does not provision the Elastic Beanstalk environments or ElastiCache/Valkey, though the application and deployment configuration reference them.

## Evidence in the repository

| Part of diagram | Source of truth |
| --- | --- |
| Browser REST commands, UI WebSocket, Redis writes/reads | [`visual_controller/app.py`](../../visual_controller/app.py), [`frontend/src/utils/api.ts`](../../visual_controller/frontend/src/utils/api.ts), [`useTankSocket.ts`](../../visual_controller/frontend/src/hooks/useTankSocket.ts) |
| Broker command stream, gateway WebSocket, status stream | [`control_broker/app.py`](../../control_broker/app.py), [`redis_listener.py`](../../control_broker/services/redis_listener.py), [`connection_manager.py`](../../control_broker/services/connection_manager.py) |
| Gateway, encrypted frame, receiver, motors | [`tx_websocket_gateway.ino`](../../tx_websocket_gateway/tx_websocket_gateway.ino), [`ControlProtocol.h`](../../common/ControlProtocol.h), [`rx_driver.ino`](../../rx_driver/rx_driver.ino), [`TankShift.cpp`](../../rx_driver/TankShift.cpp) |
| Camera encoding, relay, browser WHEP | [`sbc_streamer/main.go`](../../sbc_streamer/main.go), [`build.sh`](../../sbc_streamer/build.sh), [`media_relay/main.tf`](../../infra/terraform/media_relay/main.tf), [`mediamtx.yaml.tpl`](../../infra/terraform/media_relay/templates/mediamtx.yaml.tpl), [`useWhepPlayer.ts`](../../visual_controller/frontend/src/hooks/useWhepPlayer.ts) |
| AWS delivery | [`.github/workflows/deploy.yaml`](../../.github/workflows/deploy.yaml), [`infra/terraform/media_relay/`](../../infra/terraform/media_relay/) |

The former TeX/PDF diagram showed a direct robot-to-broker WebSocket link and has been removed; Git history retains it for reference.

## Regenerate

From the repository root, run:

```bash
./docs/architecture/render.sh
```

The two Python sources and [`svg_canvas.py`](svg_canvas.py) use only the Python standard library to write the SVGs. The AWS source embeds the versioned [AWS service icons](icons/README.md) into its SVG, so the final file is self-contained. The script then uses ImageMagick (`magick` or `convert`) to export the PNGs. Edit the Python sources and rerun the script; keep the generated SVG and PNG files in version control. The sequence source is Mermaid and can be rendered by Mermaid-compatible Markdown viewers.
