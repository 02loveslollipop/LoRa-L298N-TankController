# Radxa SBC Streamer

This Go utility supervises an `ffmpeg` process that pushes the USB camera feed from the Radxa Rock 3C to the media relay hosted at `rtsp.nene.02labs.me`.

## Prerequisites

- Go 1.22 or newer (for building the binary)
- `ffmpeg` installed on the SBC with hardware access to `/dev/video0`
- Network connectivity from the SBC to the relay host on TCP port `8554`

## Configuration

The streamer is configured through environment variables (values shown with defaults):

| Variable | Description |
| --- | --- |
| `FFMPEG_BINARY=ffmpeg` | Path to the `ffmpeg` executable |
| `CAMERA_DEVICE=/dev/video0` | Video4Linux device supplying the camera feed |
| `AUDIO_DEVICE` | Optional ALSA device (e.g. `hw:1,0`) to include audio |
| `INPUT_FORMAT` | Force a V4L2 input format (e.g. `mjpeg`, `yuyv422`) when autodetect fails |
| `FRAME_RATE=30` | Capture frame rate |
| `VIDEO_SIZE=1280x720` | Capture resolution |
| `VIDEO_BITRATE=2M` | Target average video bitrate |
| `VIDEO_MAXRATE=2M` | Peak video bitrate (CBR-style when set equal to `VIDEO_BITRATE`) |
| `VIDEO_BUFSIZE=2M` | Encoder buffer size |
| `VIDEO_CODEC=h264_rkmpp` | Video encoder (Rockchip hardware encoder by default) |
| `VIDEO_FORMAT=nv12` | Pixel format fed into the encoder |
| `VIDEO_ROTATION` | Optional rotation in degrees (90, 180, or 270) applied before encoding |
| `STREAM_NAME=robot` | Path name on the relay |
| `RELAY_HOST=rtsp.02labs.me:8554` | Relay host (host:port) |
| `RELAY_PUBLISH_USER` | Username for RTSP publish authentication |
| `RELAY_PUBLISH_PASS` | Password for RTSP publish authentication |
| `RTSP_TRANSPORT=tcp` | Transport to use when pushing (`tcp` or `udp`) |
| `AUDIO_BITRATE=128k` | Audio bitrate when audio is enabled |
| `AUDIO_SAMPLE_RATE=48000` | Audio sampling rate |
| `AUDIO_CHANNELS=2` | Number of audio channels |
| `GENERATE_SINE_AUDIO=true` | Generate a synthetic sine wave when no audio device is supplied |
| `SINE_FREQUENCY=1000` | Frequency (Hz) of the synthetic sine tone |
| `USE_TEST_PATTERN=false` | When `true`, push a `testsrc` pattern instead of the camera |

## Building

```powershell
# on the SBC or a build machine
cd sbc_streamer
go build -o streamer
```

Copy the resulting `streamer` binary to the Radxa.

## Running as a service

1. Create an environment file `/opt/streamer/streamer.env` with the variables above. Example:

   ```bash
   RELAY_PUBLISH_USER=robot
   RELAY_PUBLISH_PASS=secret
   STREAM_NAME=robot
   ```

2. Install the binary at `/opt/streamer/streamer` and make it executable.

3. Add a systemd unit (`/etc/systemd/system/robot-stream.service`):

   ```ini
   [Unit]
   Description=Robot camera RTSP uplink
   After=network.target

   [Service]
   Type=simple
   EnvironmentFile=/opt/streamer/streamer.env
   ExecStart=/opt/streamer/streamer
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now robot-stream.service
   ```

The service will restart automatically if `ffmpeg` exits and will reconnect after transient network failures.

## Hardware acceleration tips

- The default pipeline now matches the Rockchip GPU sweet spot: 1280x720 @30 fps, NV12 frames, and `h264_rkmpp` with 2 Mbps CBR.
- Ensure the SBC is running an `ffmpeg` build compiled with `--enable-rkmpp` (the provided Radxa builds usually ship this; the custom binary you installed is assumed to replace `ffmpeg`).
- Adjust the `VIDEO_*` variables if you need different bitrates or resolutions, but keep an eye on encoder limits.
- Set `USE_TEST_PATTERN=true` to emit the synthetic `testsrc` pattern while commissioning the pipeline.
