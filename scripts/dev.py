"""Build, validate, and serve the static site for local development."""

from __future__ import annotations

import argparse
import sys
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_site import build_site
from scripts.check_site import check_site


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build, validate, and preview the static catnews site."
    )
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--base-path", default="/catnews")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/catnews")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    data_dir = args.data_dir or Path(__file__).resolve().parent.parent / "data"
    build_site(data_dir, args.site, args.base_path, args.base_url)
    errors = check_site(args.site, args.base_path)
    if errors:
        for error in errors:
            print(f"[catnews] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

    with tempfile.TemporaryDirectory(prefix="catnews-preview-") as temporary:
        preview_root = Path(temporary)
        mount = preview_root / args.base_path.strip("/")
        mount.parent.mkdir(parents=True, exist_ok=True)
        mount.symlink_to(args.site.resolve(), target_is_directory=True)
        handler = partial(SimpleHTTPRequestHandler, directory=str(preview_root))
        server = ThreadingHTTPServer((args.host, args.port), handler)
        url = f"http://{args.host}:{args.port}{args.base_path.rstrip('/')}/"
        print(f"[catnews] previewing {url} (Ctrl-C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[catnews] preview stopped")
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
