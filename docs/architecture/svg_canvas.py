"""Small, dependency-free SVG primitives for the architecture diagrams."""

from __future__ import annotations

from html import escape
from math import hypot
from pathlib import Path
import re


WIDTH = 2880
HEIGHT = 1620


class Canvas:
    def __init__(self, title: str, description: str) -> None:
        self.title = title
        self.description = description
        self.elements: list[str] = []

    def raw(self, markup: str) -> None:
        self.elements.append(markup)

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: str = "white",
        stroke: str = "none",
        stroke_width: float = 1,
        radius: float = 0,
        dash: str | None = None,
    ) -> None:
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
            f'rx="{radius}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_width}"{dashed}/>'
        )

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: int = 30,
        color: str = "#14263D",
        weight: int = 400,
        anchor: str = "start",
        letter_spacing: float | None = None,
    ) -> None:
        spacing = f' letter-spacing="{letter_spacing}"' if letter_spacing is not None else ""
        self.raw(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
            f'font-family="Lato, DejaVu Sans, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}"{spacing}>{escape(value)}</text>'
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: str,
        width: float = 4,
        dash: str | None = None,
        marker: str | None = None,
    ) -> None:
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(
            f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round"{dashed}/>'
        )
        if marker:
            self._arrowhead(x1, y1, x2, y2, color)

    def _arrowhead(self, x1: float, y1: float, x2: float, y2: float, color: str) -> None:
        distance = hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / distance, (y2 - y1) / distance
        base_x, base_y = x2 - ux * 18, y2 - uy * 18
        left_x, left_y = base_x - uy * 9, base_y + ux * 9
        right_x, right_y = base_x + uy * 9, base_y - ux * 9
        self.raw(
            f'<polygon points="{x2},{y2} {left_x},{left_y} {right_x},{right_y}" '
            f'fill="{color}"/>'
        )

    def path(
        self,
        d: str,
        *,
        color: str,
        width: float = 4,
        dash: str | None = None,
        marker: str | None = None,
    ) -> None:
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(
            f'<path d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round"{dashed}/>'
        )
        if marker:
            numbers = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", d)]
            self._arrowhead(numbers[-4], numbers[-3], numbers[-2], numbers[-1], color)

    def pill(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        value: str,
        *,
        fill: str,
        color: str,
        size: int = 25,
        stroke: str | None = None,
        weight: int = 700,
    ) -> None:
        self.rect(
            x,
            y,
            width,
            height,
            fill=fill,
            stroke=stroke or fill,
            stroke_width=2 if stroke else 0,
            radius=height / 2,
        )
        self.text(x + width / 2, y + height / 2 + size * 0.35, value, size=size, color=color, weight=weight, anchor="middle")

    def card(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        eyebrow: str,
        title: str,
        subtitle: str,
        accent: str,
        title_size: int = 36,
        subtitle_size: int = 26,
        fill: str = "#FFFFFF",
        muted: bool = False,
    ) -> None:
        border = "#D7E0EA" if muted else "#CBD8E6"
        self.rect(x, y, width, height, fill=fill, stroke=border, stroke_width=2, radius=20)
        self.rect(x, y + 20, 8, height - 40, fill=accent, radius=4)
        self.text(x + 29, y + 41, eyebrow, size=22, color=accent, weight=800, letter_spacing=1.4)
        self.text(x + 29, y + 98, title, size=title_size, color="#14263D" if not muted else "#5C6D80", weight=800)
        self.text(x + 29, y + 141, subtitle, size=subtitle_size, color="#52647A" if not muted else "#78899B")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        defs = """
<defs>
  <marker id="arrow-blue" viewBox="0 0 20 20" refX="17" refY="10" markerWidth="20" markerHeight="20" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 2 L 18 10 L 1 18 Z" fill="#2365C7"/></marker>
  <marker id="arrow-teal" viewBox="0 0 20 20" refX="17" refY="10" markerWidth="20" markerHeight="20" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 2 L 18 10 L 1 18 Z" fill="#087F8C"/></marker>
  <marker id="arrow-green" viewBox="0 0 20 20" refX="17" refY="10" markerWidth="20" markerHeight="20" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 2 L 18 10 L 1 18 Z" fill="#139B87"/></marker>
  <marker id="arrow-amber" viewBox="0 0 20 20" refX="17" refY="10" markerWidth="20" markerHeight="20" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 2 L 18 10 L 1 18 Z" fill="#C87720"/></marker>
  <marker id="arrow-deploy" viewBox="0 0 20 20" refX="17" refY="10" markerWidth="20" markerHeight="20" orient="auto" markerUnits="userSpaceOnUse"><path d="M 1 2 L 18 10 L 1 18 Z" fill="#D57C22"/></marker>
</defs>"""
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="diagram-title diagram-desc">\n'
            f'<title id="diagram-title">{escape(self.title)}</title>\n'
            f'<desc id="diagram-desc">{escape(self.description)}</desc>\n'
            + defs
            + "\n"
            + "\n".join(self.elements)
            + "\n</svg>\n"
        )
        path.write_text(svg, encoding="utf-8")
