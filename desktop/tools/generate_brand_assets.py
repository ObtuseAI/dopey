"""Generate the DOPEY geometric evidence-spine D desktop assets.

The renderer uses only the Python standard library so brand generation is
deterministic and does not add image-processing dependencies to the desktop
runtime.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path


Color = tuple[int, int, int, int]

TRANSPARENT: Color = (0, 0, 0, 0)
BACKGROUND: Color = (9, 11, 13, 255)
BACKGROUND_EDGE: Color = (22, 27, 30, 255)
GRID: Color = (18, 24, 26, 255)
EVIDENCE_WHITE: Color = (232, 228, 217, 255)
SIGNAL_CELADON: Color = (156, 207, 169, 255)
TRACE_MINERAL: Color = (121, 166, 216, 255)


def _inside_rounded_square(x: float, y: float, inset: float, radius: float) -> bool:
    half_extent = 0.5 - inset
    corner_extent = half_extent - radius
    dx = max(abs(x - 0.5) - corner_extent, 0.0)
    dy = max(abs(y - 0.5) - corner_extent, 0.0)
    return dx * dx + dy * dy <= radius * radius


def _inside_ellipse_ring(x: float, y: float) -> bool:
    normalized = math.sqrt(((x - 0.335) / 0.405) ** 2 + ((y - 0.5) / 0.34) ** 2)
    return x >= 0.325 and 0.875 <= normalized <= 1.125


def _inside_horizontal_trace(
    x: float,
    y: float,
    trace_y: float,
    trace_end: float,
) -> bool:
    return 0.325 <= x <= trace_end and abs(y - trace_y) <= 0.009


def _sample_color(x: float, y: float) -> Color:
    if not _inside_rounded_square(x, y, 0.025, 0.18):
        return TRANSPARENT

    color = BACKGROUND
    if not _inside_rounded_square(x, y, 0.043, 0.165):
        color = BACKGROUND_EDGE

    grid_x = abs((x * 12.0) - round(x * 12.0))
    grid_y = abs((y * 12.0) - round(y * 12.0))
    if (grid_x < 0.012 or grid_y < 0.012) and 0.10 <= x <= 0.90 and 0.10 <= y <= 0.90:
        color = GRID

    if _inside_ellipse_ring(x, y):
        color = EVIDENCE_WHITE

    if 0.245 <= x <= 0.335 and 0.15 <= y <= 0.85:
        color = EVIDENCE_WHITE
    if 0.285 <= x <= 0.335 and 0.15 <= y <= 0.85:
        color = SIGNAL_CELADON

    traces = (
        (0.265, 0.455),
        (0.382, 0.540),
        (0.500, 0.490),
        (0.618, 0.580),
        (0.735, 0.445),
    )
    if any(
        _inside_horizontal_trace(x, y, trace_y, trace_end)
        for trace_y, trace_end in traces
    ):
        color = TRACE_MINERAL

    nodes = (0.265, 0.382, 0.500, 0.618, 0.735)
    if any(abs(x - 0.310) <= 0.023 and abs(y - node_y) <= 0.023 for node_y in nodes):
        color = SIGNAL_CELADON

    if 0.245 <= x <= 0.335 and (0.15 <= y <= 0.205 or 0.795 <= y <= 0.85):
        color = EVIDENCE_WHITE
    return color


def _average_colors(colors: list[Color]) -> Color:
    count = len(colors)
    return (
        sum(color[0] for color in colors) // count,
        sum(color[1] for color in colors) // count,
        sum(color[2] for color in colors) // count,
        sum(color[3] for color in colors) // count,
    )


def render_rgba(size: int, supersample: int) -> bytes:
    if size < 1:
        raise ValueError(f"size must be positive, received {size}")
    if supersample < 1:
        raise ValueError(f"supersample must be positive, received {supersample}")
    pixels = bytearray()
    divisor = float(size * supersample)
    for pixel_y in range(size):
        for pixel_x in range(size):
            samples: list[Color] = []
            for sample_y in range(supersample):
                for sample_x in range(supersample):
                    x = (pixel_x * supersample + sample_x + 0.5) / divisor
                    y = (pixel_y * supersample + sample_y + 0.5) / divisor
                    samples.append(_sample_color(x, y))
            pixels.extend(_average_colors(samples))
    return bytes(pixels)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(payload, checksum)
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", checksum & 0xFFFFFFFF)
    )


def encode_png(size: int, rgba: bytes) -> bytes:
    expected_length = size * size * 4
    if len(rgba) != expected_length:
        raise ValueError(
            f"RGBA length mismatch: expected={expected_length}, received={len(rgba)}"
        )
    row_width = size * 4
    scanlines = bytearray()
    for row_index in range(size):
        scanlines.append(0)
        row_start = row_index * row_width
        scanlines.extend(rgba[row_start : row_start + row_width])
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9))
        + _png_chunk(b"IEND", b"")
    )


def encode_ico(images: tuple[tuple[int, bytes], ...]) -> bytes:
    if not images:
        raise ValueError("At least one icon image is required")
    header = struct.pack("<HHH", 0, 1, len(images))
    directory = bytearray()
    payload = bytearray()
    offset = 6 + 16 * len(images)
    for size, image in images:
        dimension = 0 if size == 256 else size
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(image),
                offset,
            )
        )
        payload.extend(image)
        offset += len(image)
    return header + bytes(directory) + bytes(payload)


def brand_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="DOPEY evidence-spine D">
  <defs>
    <clipPath id="tile"><rect x="13" y="13" width="486" height="486" rx="92"/></clipPath>
  </defs>
  <g clip-path="url(#tile)">
    <rect width="512" height="512" fill="#090b0d"/>
    <path d="M0 43h512M0 85h512M0 128h512M0 171h512M0 213h512M0 256h512M0 299h512M0 341h512M0 384h512M0 427h512M0 469h512M43 0v512M85 0v512M128 0v512M171 0v512M213 0v512M256 0v512M299 0v512M341 0v512M384 0v512M427 0v512M469 0v512" stroke="#12181a" stroke-width="1"/>
    <rect x="13" y="13" width="486" height="486" rx="92" fill="none" stroke="#161b1e" stroke-width="18"/>
    <path d="M151 82h21c132 0 207 69 207 174s-75 174-207 174h-21" fill="none" stroke="#e8e4d9" stroke-width="48" stroke-linejoin="round"/>
    <path d="M126 77h46v358h-46z" fill="#e8e4d9"/>
    <path d="M146 77h26v358h-26z" fill="#9ccfa9"/>
    <g stroke="#79a6d8" stroke-width="9" stroke-linecap="square">
      <path d="M166 136h67"/><path d="M166 196h110"/><path d="M166 256h84"/><path d="M166 316h131"/><path d="M166 376h62"/>
    </g>
    <g fill="#9ccfa9">
      <rect x="147" y="124" width="24" height="24"/><rect x="147" y="184" width="24" height="24"/><rect x="147" y="244" width="24" height="24"/><rect x="147" y="304" width="24" height="24"/><rect x="147" y="364" width="24" height="24"/>
    </g>
  </g>
</svg>
"""


def main() -> int:
    desktop_root = Path(__file__).resolve().parents[1]
    assets_root = desktop_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)

    svg_path = assets_root / "dopey-control-center.svg"
    png_path = assets_root / "dopey-control-center.png"
    ico_path = assets_root / "dopey-control-center.ico"
    svg_path.write_text(brand_svg(), encoding="utf-8", newline="\n")

    png_bytes = encode_png(512, render_rgba(512, 3))
    png_path.write_bytes(png_bytes)

    icon_sizes = (16, 24, 32, 48, 64, 128, 256)
    icon_images: list[tuple[int, bytes]] = []
    for size in icon_sizes:
        supersample = 6 if size <= 32 else 4
        image = encode_png(size, render_rgba(size, supersample))
        icon_images.append((size, image))
    ico_path.write_bytes(encode_ico(tuple(icon_images)))

    result = {
        "status": "pass",
        "design": "geometric_evidence_spine_d",
        "svg": str(svg_path),
        "png": str(png_path),
        "ico": str(ico_path),
        "ico_sizes": list(icon_sizes),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
