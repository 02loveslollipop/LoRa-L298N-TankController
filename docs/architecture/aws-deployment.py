"""Render the repository-supported AWS deployment view as an editable SVG.

Evidence: .github/workflows/deploy.yaml, infra/terraform/media_relay/*,
the four service Dockerfiles/Procfiles, and Redis stream configuration.
Elastic Beanstalk and ElastiCache are used by the project; only the media
relay EC2 resources are provisioned by this repository's Terraform module.
"""

from pathlib import Path

from svg_canvas import Canvas


OUT = Path(__file__).parent / "rendered" / "aws-deployment.svg"

INK = "#14263D"
MUTED = "#52647A"
RUNTIME = "#2365C7"
MEDIA = "#087F8C"
DEPLOY = "#D57C22"
ORANGE = "#C76A21"
PURPLE = "#7754B8"
RED = "#C65353"


def service_group(c: Canvas, x: int, y: int, w: int, h: int, code: str, title: str, *, accent: str, fill: str) -> None:
    c.rect(x, y, w, h, fill=fill, stroke="#D1DDE9", stroke_width=2, radius=24)
    c.rect(x + 25, y + 24, 62, 62, fill=accent, radius=14)
    c.text(x + 56, y + 65, code, size=25 if len(code) < 3 else 21, color="#FFFFFF", weight=900, anchor="middle")
    c.text(x + 105, y + 66, title, size=34, color=INK, weight=800)


def main() -> None:
    c = Canvas(
        "Long-Range IoT Teleoperation System — AWS Deployment Architecture",
        "AWS deployment view showing Elastic Beanstalk applications, ElastiCache Valkey streams, EC2 MediaMTX with Elastic IP and Security Group, S3 deployment bundles, and GitHub Actions and Terraform delivery paths.",
    )
    c.rect(0, 0, 2880, 1620, fill="#F7F9FC")
    c.rect(80, 75, 12, 102, fill=ORANGE, radius=6)
    c.text(112, 128, "Long-Range IoT Teleoperation System", size=68, color=INK, weight=800)
    c.text(113, 180, "AWS Deployment Architecture", size=34, color=MUTED, weight=600)
    c.line(2085, 116, 2155, 116, color=RUNTIME, width=8)
    c.text(2177, 125, "Runtime traffic", size=27, color=INK, weight=700)
    c.line(2438, 116, 2508, 116, color=DEPLOY, width=8, dash="16 10")
    c.text(2530, 125, "Deployment", size=27, color=INK, weight=700)

    # External systems remain outside the AWS boundary. The lower row is the
    # delivery lane, not an AWS-managed service.
    c.rect(80, 262, 580, 1030, fill="#FFFFFF", stroke="#D1DDE9", stroke_width=2, radius=28)
    c.pill(108, 288, 58, 54, "E", fill="#E8F0FC", color=RUNTIME, size=28)
    c.text(187, 327, "EXTERNAL / EDGE", size=30, color=INK, weight=800)
    c.line(108, 356, 632, 356, color="#E4EBF3", width=2)
    c.card(112, 406, 470, 160, eyebrow="OPERATOR", title="Browser / Control UI", subtitle="Commands + live status", accent=RUNTIME, title_size=36)
    c.card(112, 680, 470, 160, eyebrow="LOCAL EDGE", title="LoRa gateway", subtitle="LilyGO T-Beam / ESP32", accent=ORANGE, title_size=37)
    c.card(112, 925, 470, 160, eyebrow="ON ROBOT", title="Radxa Rock 3C", subtitle="RTSP camera uplink", accent=MEDIA, title_size=37)
    c.card(112, 1115, 470, 165, eyebrow="OPERATOR", title="Browser playback", subtitle="WebRTC / WHEP", accent=MEDIA, title_size=34)

    c.rect(700, 262, 2100, 1260, fill="#FFFFFF", stroke="#BFCFDE", stroke_width=3, radius=28)
    c.pill(728, 288, 92, 54, "AWS", fill="#FFE9D5", color=ORANGE, size=27)
    c.text(841, 327, "AWS CLOUD", size=30, color=INK, weight=800)
    c.text(2755, 326, "Runtime resources + deployment artifacts", size=25, color=MUTED, anchor="end")
    c.line(728, 356, 2772, 356, color="#E4EBF3", width=2)

    service_group(c, 740, 385, 1160, 490, "EB", "AWS Elastic Beanstalk", accent=ORANGE, fill="#FFF9F3")
    c.card(776, 478, 506, 155, eyebrow="APPLICATION", title="Visual Controller", subtitle="API + browser WebSocket", accent=ORANGE, title_size=38)
    c.card(1356, 478, 506, 155, eyebrow="APPLICATION", title="Control Broker", subtitle="Commands + gateway WS", accent=ORANGE, title_size=38)
    c.card(776, 678, 506, 155, eyebrow="SECONDARY SERVICE", title="Stream Cleaner", subtitle="Stream retention", accent="#A8B6C7", title_size=34, muted=True)
    c.card(1356, 678, 506, 155, eyebrow="SECONDARY SERVICE", title="Telemetry Dashboard", subtitle="Monitoring view", accent="#A8B6C7", title_size=34, muted=True)

    service_group(c, 1936, 385, 826, 490, "V", "Amazon ElastiCache / Valkey", accent=PURPLE, fill="#FAF7FF")
    c.rect(1980, 500, 738, 115, fill="#FFFFFF", stroke="#D9CDEC", stroke_width=2, radius=18)
    c.text(2010, 545, "REDIS STREAM", size=23, color=PURPLE, weight=800, letter_spacing=1.1)
    c.text(2010, 589, "tank_commands", size=37, color=INK, weight=800)
    c.rect(1980, 648, 738, 115, fill="#FFFFFF", stroke="#D9CDEC", stroke_width=2, radius=18)
    c.text(2010, 693, "REDIS STREAM", size=23, color=PURPLE, weight=800, letter_spacing=1.1)
    c.text(2010, 737, "tank_status", size=37, color=INK, weight=800)
    c.text(1980, 807, "Commands: Visual Controller → Broker", size=23, color=MUTED, weight=600)
    c.text(1980, 839, "Status: Broker → Visual Controller", size=23, color=MUTED, weight=600)

    service_group(c, 1550, 924, 1212, 345, "EC2", "Amazon EC2 · media relay", accent=ORANGE, fill="#FFF9F3")
    c.card(1590, 1012, 700, 155, eyebrow="CONTAINER", title="MediaMTX", subtitle="RTSP ingest · WebRTC / HLS output", accent=ORANGE, title_size=40)
    c.rect(2326, 1012, 396, 155, fill="#FFFFFF", stroke="#D8BFA5", stroke_width=2, radius=20, dash="9 8")
    c.text(2355, 1053, "OPTIONAL", size=22, color=ORANGE, weight=800, letter_spacing=1.2)
    c.text(2355, 1105, "Caddy / TLS", size=36, color=INK, weight=800)
    c.text(2355, 1148, "WHEP + HLS HTTP proxy", size=24, color=MUTED)
    c.pill(1592, 1193, 364, 53, "EC2 Security Group", fill="#FFF0DF", color=ORANGE, size=25)
    c.pill(1982, 1193, 251, 53, "Elastic IP", fill="#FFF0DF", color=ORANGE, size=25)

    # Draw delivery links before runtime links so the solid paths remain clear
    # at their two deliberate intersections.
    c.text(108, 1342, "DELIVERY / IaC", size=24, color=DEPLOY, weight=800, letter_spacing=1.0)
    c.card(112, 1350, 287, 155, eyebrow="CI / CD", title="GitHub Actions", subtitle="Push + manual jobs", accent=DEPLOY, title_size=32, subtitle_size=24)
    c.card(429, 1350, 236, 155, eyebrow="MEDIA IaC", title="Terraform", subtitle="Manual dispatch", accent=DEPLOY, title_size=34, subtitle_size=22)
    service_group(c, 780, 1340, 510, 155, "S3", "Amazon S3", accent=RED, fill="#FFF8F8")
    c.text(810, 1469, "EB deployment bundles", size=26, color=MUTED, weight=600)

    c.line(399, 1432, 421, 1432, color=DEPLOY, width=5, dash="14 10", marker="arrow-deploy")
    c.path("M 380 1350 L 380 1294 L 990 1294 L 990 1332", color=DEPLOY, width=5, dash="14 10", marker="arrow-deploy")
    c.path("M 1015 1340 L 1015 910 L 1035 910 L 1035 875", color=DEPLOY, width=5, dash="14 10", marker="arrow-deploy")
    c.path("M 665 1430 L 690 1430 L 690 1503 L 2184 1503 L 2184 1264", color=DEPLOY, width=5, dash="14 10", marker="arrow-deploy")
    c.pill(817, 1250, 310, 48, "EB bundles / versions", fill="#FFF0DF", color=DEPLOY, size=23)
    c.pill(1704, 1432, 332, 48, "Terraform provisions relay", fill="#FFF0DF", color=DEPLOY, size=23)

    # Runtime links. The end-to-end diagram has the full directional status
    # sequence; here bidirectional labels keep the deployment view readable.
    c.line(582, 549, 783, 549, color=RUNTIME, width=6, marker="arrow-blue")
    c.pill(586, 572, 182, 47, "HTTPS / REST", fill="#E8F0FC", color=RUNTIME, size=22)
    c.path("M 1609 633 L 1609 666 L 610 666 L 610 759 L 575 759", color=RUNTIME, width=6, marker="arrow-blue")
    c.pill(190, 590, 316, 47, "Gateway status · WebSocket", fill="#E6F6F2", color="#139B87", size=22)
    c.path("M 1035 478 L 1035 466 L 1908 466 L 1908 557 L 1972 557", color=RUNTIME, width=5, marker="arrow-blue")
    c.line(1980, 591, 1858, 591, color=RUNTIME, width=5, marker="arrow-blue")
    c.path("M 350 680 L 350 642 L 1320 642 L 1320 610 L 1363 610", color="#139B87", width=5, marker="arrow-green")
    c.path("M 1862 615 L 1905 615 L 1905 706 L 1986 706", color="#139B87", width=5, marker="arrow-green")
    c.line(1980, 755, 1900, 755, color="#139B87", width=5, marker="arrow-green")
    c.line(776, 500, 575, 500, color="#139B87", width=5, marker="arrow-green")

    c.line(582, 1038, 1598, 1089, color=MEDIA, width=7, marker="arrow-teal")
    c.pill(930, 963, 375, 50, "RTSP / Internet · H.264", fill="#E5F4F3", color=MEDIA, size=24)
    c.path("M 1780 1167 L 1780 1210 L 575 1210", color=MEDIA, width=7, marker="arrow-teal")
    c.pill(920, 1138, 303, 50, "WebRTC / WHEP", fill="#E5F4F3", color=MEDIA, size=25)

    c.save(OUT)


if __name__ == "__main__":
    main()
