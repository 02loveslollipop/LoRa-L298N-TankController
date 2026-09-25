"""Render the source-verified AWS deployment topology with AWS service icons.

The icon artwork in icons/ is from the AWS Architecture Icon Package (July
2026). The layout and links are derived from the repository's deploy workflow,
media-relay Terraform, service code, and Redis stream configuration. This view
does not imply that the repository provisions its Beanstalk or Valkey resources.
"""

from pathlib import Path
import re

from svg_canvas import Canvas


HERE = Path(__file__).parent
OUT = HERE / "rendered" / "aws-deployment.svg"

INK = "#273447"
MUTED = "#536275"
RULE = "#8391A0"
CONTROL = "#3964A8"
MEDIA = "#168487"
DEPLOY = "#8A5CB0"
PALE_BLUE = "#EFF8FF"
PALE_GREEN = "#F3F9F2"
PALE_PURPLE = "#F8F5FC"


def icon(c: Canvas, name: str, x: int, y: int, size: int) -> None:
    """Inline an official AWS icon so the rendered SVG remains standalone."""
    source = (HERE / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    body = re.search(r"<svg[^>]*>(.*)</svg>", source, re.S).group(1)
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    body = "\n".join(line.rstrip() for line in body.splitlines())
    dimension = 40 if name == "aws-cloud" else 80
    c.raw(f'<g transform="translate({x} {y}) scale({size / dimension})">{body}</g>')


def heading(c: Canvas, x: int, y: int, title: str, *, color: str = INK) -> None:
    c.text(x, y, title, size=35, color=color, weight=700)


def app(c: Canvas, x: int, y: int, title: str, subtitle: str, *, secondary: bool = False) -> None:
    fill = "#F9FBFD" if secondary else "#FFFFFF"
    stroke = "#CAD7E3" if secondary else "#AFC7D8"
    c.rect(x, y, 420, 146 if not secondary else 93, fill=fill, stroke=stroke, stroke_width=2, radius=13)
    c.rect(x + 23, y + 24, 76, 76 if not secondary else 49, fill="#91A5B9" if secondary else "#ED7100", radius=11)
    # A generic application glyph avoids claiming these are separate AWS services.
    c.raw(f'<rect x="{x + 42}" y="{y + 42}" width="38" height="25" rx="3" fill="none" stroke="white" stroke-width="3"/>')
    c.line(x + 46, y + 74, x + 76, y + 74, color="#FFFFFF", width=3)
    c.text(x + 121, y + (59 if secondary else 65), title, size=32 if secondary else 35,
           color=MUTED if secondary else INK, weight=700)
    if not secondary:
        c.text(x + 121, y + 108, subtitle, size=25, color=MUTED)


def stream(c: Canvas, x: int, y: int, name: str, role: str) -> None:
    c.rect(x, y, 604, 105, fill="#FFFFFF", stroke="#C6B8DB", stroke_width=2, radius=13)
    c.rect(x + 20, y + 23, 59, 59, fill="#8C4DC2", radius=9)
    for offset in (39, 52, 65):
        c.line(x + 35, y + offset, x + 65, y + offset, color="#FFFFFF", width=3)
    c.text(x + 100, y + 47, name, size=30, color=INK, weight=750)
    c.text(x + 100, y + 80, role, size=23, color=MUTED)


def external(c: Canvas, x: int, y: int, title: str, detail: str, kind: str) -> None:
    # Simple monochrome hardware/person pictograms are intentionally distinct
    # from the colored AWS product icons inside the cloud boundary.
    if kind == "browser":
        c.rect(x, y, 92, 69, fill="#FFFFFF", stroke=INK, stroke_width=4, radius=8)
        c.line(x + 3, y + 18, x + 89, y + 18, color=INK, width=3)
        for offset in (13, 25, 37):
            c.raw(f'<circle cx="{x + offset}" cy="{y + 10}" r="3" fill="{INK}"/>')
        c.line(x + 28, y + 80, x + 64, y + 80, color=INK, width=4)
    elif kind == "chip":
        c.rect(x + 12, y + 7, 68, 68, fill="#FFFFFF", stroke=INK, stroke_width=4, radius=8)
        for offset in (25, 43, 61):
            c.line(x, y + offset, x + 12, y + offset, color=INK, width=4)
            c.line(x + 80, y + offset, x + 92, y + offset, color=INK, width=4)
        c.raw(f'<circle cx="{x + 46}" cy="{y + 41}" r="13" fill="none" stroke="{INK}" stroke-width="4"/>')
    c.text(x + 46, y + 126, title, size=32, color=INK, weight=700, anchor="middle")
    c.text(x + 46, y + 162, detail, size=23, color=MUTED, anchor="middle")


def label(c: Canvas, x: int, y: int, value: str, *, color: str = MUTED, size: int = 24) -> None:
    c.text(x, y, value, size=size, color=color, weight=650)


def main() -> None:
    c = Canvas(
        "Long-Range IoT Teleoperation System — AWS Deployment Architecture",
        "AWS Cloud with Elastic Beanstalk applications, ElastiCache Valkey command and status streams, EC2 MediaMTX relay, S3 deployment bundles, and separate runtime and deployment links. External browser, gateway, and Radxa systems are outside AWS.",
    )
    c.rect(0, 0, 2880, 1620, fill="#FFFFFF")
    c.text(100, 120, "Long-Range IoT Teleoperation System", size=66, color=INK, weight=800)
    c.text(101, 183, "AWS Deployment Architecture", size=38, color=MUTED, weight=600)
    c.line(2050, 130, 2120, 130, color=RULE, width=4)
    label(c, 2141, 140, "Runtime", size=25)
    c.line(2325, 130, 2395, 130, color=DEPLOY, width=4, dash="11 8")
    label(c, 2416, 140, "Deployment", size=25)

    # External systems; playback is shown as a second port of the same browser.
    label(c, 105, 318, "EXTERNAL / EDGE", color=INK, size=29)
    external(c, 255, 417, "Browser operator", "Control + live status", "browser")
    external(c, 255, 699, "LoRa gateway", "WebSocket client", "chip")
    external(c, 255, 998, "Radxa Rock 3C", "RTSP video uplink", "chip")
    external(c, 255, 1171, "Browser playback", "Same operator · WHEP", "browser")

    # Cloud boundary and three actual resource groups. No VPC, subnet, ALB,
    # API Gateway, or orchestration service is asserted by repository evidence.
    c.rect(605, 260, 2195, 1070, fill="#FFFFFF", stroke="#8090A2", stroke_width=3)
    icon(c, "aws-cloud", 605, 260, 82)
    heading(c, 710, 315, "AWS Cloud")

    c.rect(700, 386, 1255, 510, fill=PALE_BLUE, stroke="#B7D2E5", stroke_width=2, radius=15)
    icon(c, "elastic-beanstalk", 733, 418, 92)
    heading(c, 847, 471, "AWS Elastic Beanstalk")
    app(c, 788, 560, "Visual Controller", "Browser API + UI WebSocket")
    app(c, 1434, 560, "Control Broker", "Command and gateway WS")
    app(c, 788, 772, "Stream Cleaner", "", secondary=True)
    app(c, 1434, 772, "Telemetry Dashboard", "", secondary=True)

    c.rect(2000, 386, 728, 510, fill=PALE_PURPLE, stroke="#D7C6E8", stroke_width=2, radius=15)
    icon(c, "elasticache", 2034, 418, 92)
    heading(c, 2148, 471, "Amazon ElastiCache")
    label(c, 2149, 507, "Redis-compatible Valkey", size=25)
    stream(c, 2056, 566, "tank_commands", "Visual Controller → Control Broker")
    stream(c, 2056, 728, "tank_status", "Control Broker → Visual Controller")

    c.rect(700, 975, 1280, 310, fill=PALE_GREEN, stroke="#BED5C8", stroke_width=2, radius=15)
    icon(c, "ec2", 732, 1008, 92)
    heading(c, 846, 1061, "Amazon EC2 · media relay")
    c.rect(902, 1102, 470, 97, fill="#FFFFFF", stroke="#B7CDBE", stroke_width=2, radius=12)
    heading(c, 934, 1159, "MediaMTX container")
    c.rect(1422, 1102, 444, 97, fill="#FFFFFF", stroke="#B7CDBE", stroke_width=2, radius=12, dash="9 8")
    heading(c, 1453, 1145, "Caddy / TLS")
    label(c, 1454, 1177, "optional HTTP proxy", size=22)
    label(c, 1145, 1250, "EC2 Security Group  ·  Elastic IP", size=25)

    c.rect(2028, 975, 700, 310, fill="#F5F9EF", stroke="#C4D8B1", stroke_width=2, radius=15)
    icon(c, "s3", 2061, 1008, 92)
    heading(c, 2175, 1061, "Amazon S3")
    c.text(2080, 1157, "Elastic Beanstalk", size=33, color=INK, weight=700)
    c.text(2080, 1204, "deployment bundles", size=33, color=INK, weight=700)

    # Runtime: HTTPS and browser UI WebSocket at left; the Valkey stream links
    # follow the actual command/status direction. A paired arrow marks the
    # command and gateway-reported status on the same gateway WebSocket.
    c.path("M 460 507 L 675 507 L 675 599 L 788 599", color=RULE, width=4, marker="arrow-blue")
    label(c, 499, 488, "HTTPS / REST", color=CONTROL)
    c.path("M 788 680 L 574 680 L 574 560 L 460 560", color=RULE, width=4, marker="arrow-blue")
    label(c, 583, 662, "UI WebSocket", color=CONTROL)

    c.path("M 1000 560 L 1000 534 L 2025 534 L 2025 617 L 2056 617", color=RULE, width=4, marker="arrow-blue")
    label(c, 1558, 520, "Redis Streams", color=CONTROL)
    c.line(2056, 650, 1854, 650, color=RULE, width=4, marker="arrow-blue")
    c.path("M 1854 696 L 1974 696 L 1974 776 L 2056 776", color=RULE, width=4, marker="arrow-blue")
    c.path("M 2056 833 L 1980 833 L 1980 746 L 1000 746 L 1000 706", color=RULE, width=4, marker="arrow-blue")

    c.path("M 460 778 L 545 778 L 545 927 L 1968 927 L 1968 640 L 1854 640", color=RULE, width=4, marker="arrow-blue")
    c.line(545, 778, 460, 778, color=RULE, width=4, marker="arrow-blue")
    label(c, 740, 918, "WebSocket · commands / gateway status", color=CONTROL)

    # The media plane stays below the control services. Browser playback uses
    # WHEP, while the Radxa uplink is RTSP/H.264.
    c.path("M 460 1088 L 874 1088 L 874 1150 L 902 1150", color=MEDIA, width=5, marker="arrow-teal")
    label(c, 530, 1073, "RTSP · H.264", color=MEDIA)
    c.path("M 1000 1199 L 1000 1238 L 460 1238", color=MEDIA, width=5, marker="arrow-teal")
    label(c, 555, 1223, "WebRTC / WHEP", color=MEDIA)

    # Delivery sits outside the runtime resource groups. The push workflow
    # uploads bundles to S3 and updates EB; manual dispatch runs Terraform.
    c.rect(1980, 1404, 317, 139, fill="#FFFFFF", stroke="#C9D1DC", stroke_width=2, radius=13)
    c.rect(2000, 1426, 75, 75, fill="#242F3E", radius=11)
    c.text(2038, 1477, "GH", size=30, color="#FFFFFF", weight=800, anchor="middle")
    c.text(2093, 1462, "GitHub", size=33, color=INK, weight=700)
    c.text(2093, 1503, "Actions", size=33, color=INK, weight=700)

    c.rect(2425, 1404, 320, 139, fill="#FFFFFF", stroke="#C9D1DC", stroke_width=2, radius=13)
    c.rect(2445, 1426, 75, 75, fill="#844FBA", radius=11)
    c.text(2483, 1477, "T", size=39, color="#FFFFFF", weight=800, anchor="middle")
    c.text(2536, 1483, "Terraform", size=33, color=INK, weight=700)

    c.line(2160, 1404, 2160, 1285, color=DEPLOY, width=4, dash="11 8", marker="arrow-deploy")
    label(c, 2030, 1375, "EB bundles", color=DEPLOY)
    c.path("M 2395 975 L 2395 945 L 1980 945 L 1980 908 L 1938 908", color=DEPLOY, width=4, dash="11 8", marker="arrow-deploy")
    label(c, 2176, 934, "EB deploy", color=DEPLOY, size=22)
    c.line(2297, 1474, 2425, 1474, color=DEPLOY, width=4, dash="11 8", marker="arrow-deploy")
    c.path("M 2585 1543 L 2585 1570 L 1742 1570 L 1742 1285", color=DEPLOY, width=4, dash="11 8", marker="arrow-deploy")
    label(c, 1370, 1555, "provisions EC2 relay", color=DEPLOY, size=23)

    c.save(OUT)


if __name__ == "__main__":
    main()
