from __future__ import annotations

import struct
import zlib

WIDTH = 1200
HEIGHT = 630

PAPER = (245, 244, 237)
INK = (35, 36, 31)
INK_SOFT = (63, 65, 58)

_TEXT = "CATNEWS"
_WORDMARK_SCALE = 8
_CAPTION_DATE_SCALE = 4
_CAPTION_COUNT_SCALE = 3

# 5x7 bitmap glyphs — the caption has no font dependencies at build time.
_FONT: dict[str, tuple[str, ...]] = {
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "W": ("10001", "10001", "10001", "10001", "10101", "11011", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}

# Paw blobs echoing the catnews mark, in the source badge palette.
_PAWS: list[tuple[int, tuple[int, int, int]]] = [
    (180, (0x9C, 0x4D, 0x14)),
    (416, (0x2E, 0x6B, 0x3E)),
    (784, (0x20, 0x50, 0x7A)),
    (1020, (0x8A, 0x1F, 0x18)),
]


def hex_rgb(value: str) -> tuple[int, int, int]:
    """Parse a #RRGGBB hex color into an (r, g, b) tuple."""
    hexstr = value.lstrip("#")
    return (int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16))


class _Canvas:
    """Minimal RGBA raster with draw helpers (no Pillow dependency)."""

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self.rows = [bytearray([*PAPER, 255] * w) for _ in range(h)]

    def set_px(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x * 4 : x * 4 + 4] = bytes((*color, 255))

    def fill_ellipse(self, cx: int, cy: int, rx: int, ry: int, color) -> None:
        for dy in range(-ry, ry + 1):
            y = cy + dy
            if not (0 <= y < self.h):
                continue
            for dx in range(-rx, rx + 1):
                if (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1.0:
                    self.set_px(cx + dx, y, color)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color) -> None:
        for y in range(y0, y1 + 1):
            if not (0 <= y < self.h):
                continue
            for x in range(x0, x1 + 1):
                self.set_px(x, y, color)

    def text(self, text: str, scale: int, y0: int, color) -> None:
        glyph_w, glyph_h, spacing = 5, 7, 1
        total = len(text) * glyph_w * scale + (len(text) - 1) * spacing * scale
        x = (self.w - total) // 2
        for idx, ch in enumerate(text):
            glyph = _FONT.get(ch.upper())
            if glyph is None:
                continue
            gx = x + idx * (glyph_w + spacing) * scale
            for gy in range(glyph_h):
                for gxx in range(glyph_w):
                    if glyph[gy][gxx] != "1":
                        continue
                    ox = gx + gxx * scale
                    oy = y0 + gy * scale
                    for sy in range(scale):
                        for sx in range(scale):
                            self.set_px(ox + sx, oy + sy, color)

    def png(self) -> bytes:
        raw = b"".join(b"\x00" + bytes(row) for row in self.rows)
        png = b"\x89PNG\r\n\x1a\n"
        png += _chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
        png += _chunk(b"IDAT", zlib.compress(raw, 9))
        png += _chunk(b"IEND", b"")
        return png


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _paws(canvas: _Canvas) -> None:
    for cx, color in _PAWS:
        canvas.fill_ellipse(cx, 548, 46, 46, color)


def render_og_image(
    *,
    date_line: str | None = None,
    count_line: str | None = None,
    accent: tuple[int, int, int] | None = None,
) -> bytes:
    """Render a 1200x630 social card.

    The classic brand-only card (wordmark + paw blobs) is used when no
    caption is given. Passing ``date_line`` and/or ``count_line`` adds an
    edition caption: wordmark moved up, a short accent rule in the source's
    badge color, and the date / story count beneath it — so each day's
    snapshot page shares a card that identifies the edition.
    """
    canvas = _Canvas(WIDTH, HEIGHT)
    glyph_h = 7

    captioned = date_line is not None or count_line is not None
    if captioned:
        wordmark_y0 = (HEIGHT - glyph_h * _WORDMARK_SCALE) // 2 - 120
        accent_rgb = accent or INK
        # Accent rule under the wordmark.
        rule_h = 5
        rule_y = wordmark_y0 + glyph_h * _WORDMARK_SCALE + 40
        canvas.fill_rect(
            WIDTH // 2 - 64, rule_y, WIDTH // 2 + 64, rule_y + rule_h, accent_rgb
        )
        canvas.text(_TEXT, _WORDMARK_SCALE, wordmark_y0, INK)
        if date_line:
            canvas.text(date_line, _CAPTION_DATE_SCALE, rule_y + rule_h + 22, INK)
        if count_line:
            canvas.text(
                count_line, _CAPTION_COUNT_SCALE, rule_y + rule_h + 96, INK_SOFT
            )
    else:
        canvas.text(
            _TEXT,
            _WORDMARK_SCALE,
            (HEIGHT - glyph_h * _WORDMARK_SCALE) // 2 - 24,
            INK,
        )
    _paws(canvas)
    return canvas.png()
