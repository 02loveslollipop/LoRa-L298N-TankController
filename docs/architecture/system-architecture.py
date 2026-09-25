"""Render the audited end-to-end container view as an editable SVG.

Evidence: visual_controller/app.py, control_broker/app.py and services/,
tx_websocket_gateway/tx_websocket_gateway.ino, rx_driver/rx_driver.ino,
common/ControlProtocol.h, sbc_streamer/main.go, media relay Terraform,
and visual_controller/frontend/src/hooks/useWhepPlayer.ts.
"""

from pathlib import Path

from svg_canvas import Canvas


OUT = Path(__file__).parent / "rendered" / "system-architecture.svg"

BLUE = "#2365C7"
GREEN = "#139B87"
TEAL = "#087F8C"
AMBER = "#C87720"
INK = "#14263D"
MUTED = "#52647A"


def zone(c: Canvas, x: int, width: int, letter: str, name: str) -> None:
    c.rect(x, 262, width, 1220, fill="#FFFFFF", stroke="#D2DDE9", stroke_width=2, radius=28)
    c.pill(x + 28, 289, 50, 50, letter, fill="#EAF1FB", color=BLUE, size=27)
    heading_size = 23 if name == "LOCAL LORA GATEWAY" else (27 if name == "REMOTE OPERATOR" else 29)
    c.text(x + 95, 326, name, size=heading_size, color=INK, weight=800, letter_spacing=0.6)
    c.line(x + 28, 355, x + width - 28, 355, color="#E4EBF3", width=2)


def main() -> None:
    c = Canvas(
        "Long-Range IoT Teleoperation System — End-to-End Architecture",
        "Browser commands use a cloud Redis and WebSocket control path, a separate LoRa gateway, and the robot motor driver. Gateway status returns through Redis. Robot video uses a Radxa to MediaMTX RTSP path and WebRTC browser playback.",
    )
    c.rect(0, 0, 2880, 1620, fill="#F7F9FC")
    c.rect(80, 75, 12, 102, fill=BLUE, radius=6)
    c.text(112, 128, "Long-Range IoT Teleoperation System", size=68, color=INK, weight=800)
    c.text(113, 180, "End-to-End Architecture", size=34, color=MUTED, weight=600)
    c.line(2050, 116, 2122, 116, color=BLUE, width=8)
    c.text(2144, 125, "Command / control", size=27, color=INK, weight=700)
    c.line(2445, 116, 2517, 116, color=TEAL, width=8)
    c.text(2539, 125, "Video / media", size=27, color=INK, weight=700)

    zone(c, 80, 450, "A", "REMOTE OPERATOR")
    zone(c, 560, 1055, "B", "AWS / CLOUD CONTROL")
    zone(c, 1645, 450, "C", "LOCAL LORA GATEWAY")
    zone(c, 2125, 675, "D", "MOBILE ROBOT")

    c.pill(108, 376, 366, 48, "COMMAND / CONTROL PLANE", fill="#E7F0FE", color=BLUE, size=24)
    c.card(112, 438, 386, 170, eyebrow="OPERATOR", title="Browser / Control UI", subtitle="Commands + live status", accent=BLUE, title_size=34)
    c.card(590, 438, 280, 170, eyebrow="WEB SERVICE", title="Visual Controller", subtitle="REST + UI WebSocket", accent=BLUE, title_size=34, subtitle_size=24)
    c.card(942, 438, 290, 170, eyebrow="EVENT BUS", title="Redis Streams", subtitle="ElastiCache / Valkey", accent="#7259BC", title_size=35)
    c.card(1304, 438, 280, 170, eyebrow="WEB SERVICE", title="Control Broker", subtitle="Stream reader + WS", accent=BLUE, title_size=34)
    c.card(1675, 438, 390, 170, eyebrow="LOCAL EDGE", title="LilyGO T-Beam", subtitle="ESP32 · WS client · LoRa TX", accent=AMBER, title_size=36, subtitle_size=25)
    c.card(2152, 438, 270, 170, eyebrow="ON ROBOT", title="LoRa receiver", subtitle="LilyGO / ESP32", accent=AMBER, title_size=34)
    c.card(2482, 438, 290, 170, eyebrow="DRIVE", title="L298N driver", subtitle="PWM + direction", accent=AMBER, title_size=35)
    c.card(2482, 661, 290, 170, eyebrow="ACTUATORS", title="Left + right motors", subtitle="Tracked drive", accent=AMBER, title_size=30)

    # Forward control links. Labels sit in a dedicated row to keep cards readable.
    for start, end in ((498, 590), (870, 942), (1232, 1304), (1584, 1675)):
        c.line(start, 523, end - 7, 523, color=BLUE, width=6, marker="arrow-blue")
    c.line(2065, 523, 2144, 523, color=AMBER, width=7, marker="arrow-amber")
    c.line(2422, 523, 2474, 523, color=AMBER, width=6, marker="arrow-amber")
    c.line(2627, 608, 2627, 653, color=AMBER, width=6, marker="arrow-amber")

    c.pill(452, 627, 230, 50, "HTTPS / REST", fill="#E7F0FE", color=BLUE, size=25)
    c.pill(884, 627, 407, 50, "Redis Streams · commands", fill="#E7F0FE", color=BLUE, size=25)
    c.pill(1530, 627, 205, 50, "WebSocket", fill="#E7F0FE", color=BLUE, size=25)
    c.pill(2057, 627, 112, 50, "LoRa", fill="#FFF1DE", color=AMBER, size=26)
    c.pill(1968, 688, 290, 52, "Field-tested ~1.5 km", fill="#FFF1DE", color=AMBER, size=24)

    # The receive-only robot firmware does not send an acknowledgement. These
    # chips are a second view of the same cloud/gateway components above.
    c.rect(108, 759, 1972, 174, fill="#F0FBF8", stroke="#9AD9CC", stroke_width=2, radius=21)
    c.text(132, 798, "GATEWAY STATUS RETURN", size=25, color=GREEN, weight=800, letter_spacing=1.2)
    c.text(760, 798, "WebSocket → tank_status → UI WebSocket", size=25, color=MUTED, weight=600)
    chips = [
        (132, 290, "Browser"),
        (493, 290, "Visual Controller"),
        (853, 290, "tank_status"),
        (1213, 290, "Control Broker"),
        (1574, 480, "Gateway status"),
    ]
    for x, width, label in chips:
        c.pill(x, 817, width, 61, label, fill="#FFFFFF", color="#167C6D", size=25, stroke="#A7DCD0", weight=700)
    for left, right in ((422, 493), (783, 853), (1143, 1213), (1503, 1574)):
        c.line(right - 9, 847, left + 8, 847, color=GREEN, width=5, marker="arrow-green")
    c.text(132, 914, "Gateway-originated status; the robot receiver has no radio acknowledgement.", size=22, color="#5B746D")

    c.line(108, 987, 2772, 987, color="#B8DCD9", width=3)
    c.pill(108, 1010, 308, 48, "VIDEO / MEDIA PLANE", fill="#E4F5F3", color=TEAL, size=24)
    c.text(445, 1043, "Direct Internet uplink through MediaMTX · separate from command delivery", size=27, color=MUTED, weight=600)

    c.card(112, 1137, 386, 170, eyebrow="OPERATOR", title="Browser playback", subtitle="WebRTC / WHEP", accent=TEAL, title_size=35)
    c.card(787, 1137, 420, 170, eyebrow="AWS EC2", title="MediaMTX relay", subtitle="RTSP ingest · WebRTC out", accent=TEAL, title_size=37)
    c.card(2258, 1119, 416, 170, eyebrow="ON ROBOT", title="Radxa Rock 3C", subtitle="FFmpeg · H.264 encoder", accent=TEAL, title_size=37)
    c.card(2258, 1311, 416, 150, eyebrow="ON ROBOT", title="USB camera", subtitle="V4L2 capture", accent=TEAL, title_size=36)

    c.line(787, 1221, 506, 1221, color=TEAL, width=7, marker="arrow-teal")
    c.pill(521, 1065, 260, 49, "WebRTC / WHEP", fill="#E4F5F3", color=TEAL, size=25)
    c.line(2258, 1221, 1215, 1221, color=TEAL, width=7, marker="arrow-teal")
    c.pill(1564, 1137, 314, 53, "RTSP / Internet · H.264", fill="#E4F5F3", color=TEAL, size=24)
    c.line(2674, 1386, 2739, 1386, color=TEAL, width=5)
    c.line(2739, 1386, 2739, 1203, color=TEAL, width=5)
    c.line(2739, 1203, 2682, 1203, color=TEAL, width=5, marker="arrow-teal")
    c.pill(2684, 1265, 92, 46, "USB", fill="#E4F5F3", color=TEAL, size=23)

    c.line(108, 1515, 2772, 1515, color="#D7E1EA", width=2)
    c.text(110, 1561, "LoRa frame: 16 bytes · AES-256-CBC · CRC32 · duplicate sequence check", size=26, color=MUTED, weight=600)
    c.text(2770, 1561, "Field range reported from project test", size=22, color="#738296", anchor="end")
    c.save(OUT)


if __name__ == "__main__":
    main()
