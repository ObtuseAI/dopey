"""Stdlib chart renderer for HTML and PNG market-vision artifacts."""
from __future__ import annotations

import html
import struct
import zlib
from pathlib import Path

from dopey_wealth_engine.common import ensure_directory, write_json


def render_chart_artifacts(symbol: str, rows: list[dict], features: list[dict], html_path: Path, png_path: Path, spec_path: Path) -> dict:
    ensure_directory(html_path.parent)
    ensure_directory(png_path.parent)
    closes = [float(row["close"]) for row in rows[-180:]]
    dates = [row["date"] for row in rows[-180:]]
    svg = _line_svg(closes, 960, 420, "#14532d")
    latest = features[-1] if features else {}
    html_doc = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>DOPEY {html.escape(symbol)} Chart Vision</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#111;background:#f8fafc}}table{{border-collapse:collapse}}td,th{{border:1px solid #cbd5e1;padding:6px 8px}}</style></head>
<body>
<h1>{html.escape(symbol)} Market Vision</h1>
<p>Paper-only market vision chart. Live trading and broker connections are disabled.</p>
{svg}
<table><tbody>
<tr><th>Close</th><td>{latest.get("close", "")}</td></tr>
<tr><th>Trend</th><td>{latest.get("trend_regime", "")}</td></tr>
<tr><th>Volatility</th><td>{latest.get("volatility_regime", "")}</td></tr>
<tr><th>RSI</th><td>{latest.get("rsi_14", "")}</td></tr>
<tr><th>MACD</th><td>{latest.get("macd", "")}</td></tr>
</tbody></table>
</body></html>
"""
    html_path.write_text(html_doc, encoding="utf-8")
    _write_line_png(png_path, closes, 960, 420)
    spec = {
        "artifact_type": "chart_spec",
        "symbol": symbol,
        "date_start": dates[0] if dates else "",
        "date_end": dates[-1] if dates else "",
        "html_path": str(html_path),
        "png_path": str(png_path),
        "indicators": ["sma_8", "sma_21", "sma_50", "sma_200", "vwap_proxy", "atr_14", "realized_vol_21", "bollinger", "rsi_14", "macd"],
        "paper_only": True,
        "live_blocked": True,
    }
    write_json(spec_path, spec)
    return spec


def _line_svg(values: list[float], width: int, height: int, color: str) -> str:
    if not values:
        return "<svg></svg>"
    ymin = min(values)
    ymax = max(values)
    span = ymax - ymin if ymax > ymin else 1.0
    points: list[str] = []
    for index, value in enumerate(values):
        x = 20 + index * ((width - 40) / max(1, len(values) - 1))
        y = height - 20 - ((value - ymin) / span) * (height - 40)
        points.append(f"{x:.2f},{y:.2f}")
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img"><rect width="{width}" height="{height}" fill="#ffffff"/><polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(points)}"/></svg>'


def _write_line_png(path: Path, values: list[float], width: int, height: int) -> None:
    pixels = bytearray([255, 255, 255] * width * height)
    if values:
        ymin = min(values)
        ymax = max(values)
        span = ymax - ymin if ymax > ymin else 1.0
        points: list[tuple[int, int]] = []
        for index, value in enumerate(values):
            x = int(10 + index * ((width - 20) / max(1, len(values) - 1)))
            y = int(height - 10 - ((value - ymin) / span) * (height - 20))
            points.append((x, y))
        for start, end in zip(points, points[1:]):
            _draw_line(pixels, width, height, start, end, (20, 83, 45))
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        offset = row * width * 3
        raw.extend(pixels[offset:offset + width * 3])
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b"")
    path.write_bytes(png)


def _draw_line(pixels: bytearray, width: int, height: int, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int]) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            index = (y0 * width + x0) * 3
            pixels[index:index + 3] = bytes(color)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

