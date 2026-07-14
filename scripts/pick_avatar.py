#!/usr/bin/env python3
"""Randomly select one HeyGen avatar id for a render.

Two sources, in priority order:
  1. A configured pool: config JSON with heygen.avatar_pool = [ids...], or --pool
     given repeatedly on the command line.
  2. Dynamic discovery: JSON piped on stdin (the output of HeyGen's
     list_avatar_looks / list_avatar_groups). The script walks common shapes and
     collects any "avatar_id" / "id" / "look_id" values it finds.

Usage:
    python3 pick_avatar.py --config config.json < avatars.json
    python3 pick_avatar.py --pool id1 --pool id2
    python3 pick_avatar.py --seed 7 < avatars.json      # reproducible pick

Prints a JSON line:
    {"avatar_id": "...", "source": "pool|dynamic", "candidates": N}
Exit code is non-zero when no candidates are found.
"""
import argparse
import json
import random
import sys

ID_KEYS = ("avatar_id", "id", "look_id", "avatar_look_id")


def collect_ids(node, out):
    """Recursively harvest avatar-id-like strings from an arbitrary JSON blob."""
    if isinstance(node, dict):
        for key in ID_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val:
                out.append(val)
                break
        for value in node.values():
            collect_ids(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_ids(item, out)


def load_pool_from_config(path):
    if not path:
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh).get("heygen", {}).get("avatar_pool", []) or []


def main():
    ap = argparse.ArgumentParser(description="Randomly pick a HeyGen avatar id")
    ap.add_argument("--config", help="JSON config file (heygen.avatar_pool)")
    ap.add_argument("--pool", action="append", default=[], help="Explicit avatar id (repeatable)")
    ap.add_argument("--seed", type=int, help="Seed for reproducible selection")
    args = ap.parse_args()

    pool = list(args.pool) or load_pool_from_config(args.config)
    source = "pool"

    if not pool:
        raw = sys.stdin.read().strip()
        if not raw:
            sys.exit("ERROR: no --pool, no config pool, and nothing on stdin to pick from.")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.exit(f"ERROR: stdin is not valid JSON: {exc}")
        found = []
        collect_ids(data, found)
        # de-dupe, preserve order
        seen = set()
        pool = [x for x in found if not (x in seen or seen.add(x))]
        source = "dynamic"

    if not pool:
        sys.exit("ERROR: no avatar candidates found.")

    rng = random.Random(args.seed)
    choice = rng.choice(pool)
    print(json.dumps({"avatar_id": choice, "source": source, "candidates": len(pool)}))


if __name__ == "__main__":
    main()
