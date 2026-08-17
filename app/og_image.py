from __future__ import annotations

import struct
import zlib

WIDTH = 1200
HEIGHT = 630

PAPER = (245, 244, 237)
INK = (35, 36, 31)

_TEXT = "CATNEWS"
_SCALE = 8

# 5x7 bitmap glyphs — the full title has no font dependencies at build time.
_FONT: dict[str, tuple[str, ...]] = {
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "W": ("10001", "10001", "10001", "10001", "10101", "11011", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
}

# Paw blobs echoing the catnews mark, in the source badge palette.
_PAWS: list[tuple[int, tuple[int, int, int]]] = [
    (180, (0x9C, 0x4D, 0x14)),
    (416, (0x2E, 0x6B, 0x3E)),
    (784, (0x20, 0x50, 0x7A)),
    (1020, (0x8A, 0x1F, 0x18)),
]


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def render_og_image() -> bytes:
    """Render the 1200x630 social card (catnews wordmark + paw blobs)."""
    w, h = WIDTH, HEIGHT
    rows = [bytearray([*PAPER, 255] * w) for _ in range(h)]

    def set_px(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < w and 0 <= y < h:
            rows[y][x * 4 : x * 4 + 4] = bytes((*color, 255))

    def fill_ellipse(cx: int, cy: int, rx: int, ry: int, color) -> None:
        for dy in range(-ry, ry + 1):
            y = cy + dy
            if not (0 <= y < h):
                continue
            for dx in range(-rx, rx + 1):
                if (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0:
                    set_px(cx + dx, y, color)

    glyph_w, glyph_h, spacing = 5, 7, 1
    total = len(_TEXT) * glyph_w * _SCALE + (len(_TEXT) - 1) * spacing * _SCALE
    x0 = (w - total) // 2
    y0 = (h - glyph_h * _SCALE) // 2 - 24
    for idx, ch in enumerate(_TEXT):
        gx = x0 + idx * (glyph_w + spacing) * _SCALE
        for gy in range(glyph_h):
            for gxx in range(glyph_w):
                if _FONT[ch][gy][gxx] != "1":
                    continue
                ox = gx + gxx * _SCALE
                oy = y0 + gy * _SCALE
                for sy in range(_SCALE):
                    for sx in range(_SCALE):
                        set_px(ox + sx, oy + sy, INK)

    for cx, color in _PAWS:
        fill_ellipse(cx, 548, 46, 46, color)

    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 9))
    png += _chunk(b"IEND", b"")
    return png
