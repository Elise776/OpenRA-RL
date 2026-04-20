#!/usr/bin/env python3
"""Minimal end-to-end test for the GetFrame RPC.

Prerequisite: the OpenRA game process must be running in NON-headless mode
(GameConfig.headless=false → Game.Platform=Default) with the gRPC bridge
exposed on port 9999. The easiest way is:

    python -m openra_env.cli.run --config examples/config-live.yaml

…in one terminal, then in another:

    python test_capture_frame.py [--out frame.png] [--max-width 1024]

The script creates a session (multi-session mode) or reuses the active
legacy session (empty session_id), requests one rendered frame via
`BridgeClient.get_frame`, and writes the raw PNG bytes to disk so you
can open it and confirm the pixels match what you see on screen.
"""
import argparse
import sys
import time

from openra_env.server.bridge_client import BridgeClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--out", default="frame.png")
    ap.add_argument("--max-width", type=int, default=0,
                    help="Downsample width (0 = native).")
    ap.add_argument("--session-id", default="",
                    help="Session id (empty = legacy single-session mode).")
    ap.add_argument("--warmup-ticks", type=int, default=0,
                    help="FastAdvance this many ticks before capturing.")
    args = ap.parse_args()

    client = BridgeClient(host=args.host, port=args.port,
                          session_id=args.session_id, timeout_s=30.0)

    print(f"Connecting to {args.host}:{args.port}...")
    if not client.wait_for_ready(max_retries=30, retry_interval=1.0):
        print("ERROR: bridge did not become ready", file=sys.stderr)
        return 1

    if args.warmup_ticks > 0:
        print(f"Advancing {args.warmup_ticks} ticks to let render settle...")
        client.fast_advance_unary(args.warmup_ticks, [])
        time.sleep(0.2)

    print(f"Requesting frame (max_width={args.max_width})...")
    result = client.get_frame(max_width=args.max_width, timeout_s=15.0)

    print(
        f"  headless={result['headless']} "
        f"tick={result['tick']} "
        f"size={result['width']}x{result['height']} "
        f"bytes={len(result['image'])}"
    )

    if result["headless"]:
        print("ERROR: game reports headless — start the game with "
              "headless=false (Game.Platform=Default) and retry.",
              file=sys.stderr)
        return 2

    if not result["image"]:
        print("ERROR: empty image payload (renderer likely not yet ready).",
              file=sys.stderr)
        return 3

    with open(args.out, "wb") as fh:
        fh.write(result["image"])
    print(f"Saved {len(result['image'])} bytes → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
