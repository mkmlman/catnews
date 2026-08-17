from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.og_image import render_og_image

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "og.png"


def main() -> None:
    OUT.write_bytes(render_og_image())
    print(f"[catnews] wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
