from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from fetch import capture_feed_html, login

def _config() -> dict:
    with open("config.toml", "rb") as f:
        return tomllib.load(f)

def cmd_login(cfg: dict, args) -> int:
    url = args.group or cfg["groups"][0]["url"]
    login(url)
    print("login OK — profile saved to data/browser-profile")
    return 0

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="social-listening")
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("login", help="open browser, log in, save profile")
    lg.add_argument("--group", default=None)

    cap = sub.add_parser("capture", help="save raw feed HTML for parser debugging")
    cap.add_argument("--group", required=True)
    cap.add_argument("--out", default="data/sample.html")

    args = p.parse_args(argv)
    cfg = _config()
    if args.cmd == "login":
        return cmd_login(cfg, args)
    if args.cmd == "capture":
        capture_feed_html(args.group, out_path=Path(args.out))
        print(f"saved {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
