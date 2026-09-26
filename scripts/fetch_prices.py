#!/usr/bin/env python3
"""Fetch TGJU prices (currencies + coins + gold/silver) into one JSON file."""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

SOURCES = {
    "currencies": {"url": "https://www.tgju.org/currency",   "flag": True},
    "coins":      {"url": "https://www.tgju.org/coin",       "flag": False},
    "gold":       {"url": "https://www.tgju.org/gold-chart", "flag": False},
}

RE_WITH_FLAG = re.compile(
    rb'data-market-nameslug="([^"]+)"[^>]*data-price="([^"]*)".*?<th>.*?</span>\s*([^<]+?)\s*</th>',
    re.DOTALL,
)
RE_SIMPLE = re.compile(
    rb'data-market-nameslug="([^"]+)"[^>]*data-price="([^"]*)".*?<th>\s*([^<]+?)\s*</th>',
    re.DOTALL,
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse(html: bytes, with_flag: bool):
    pattern = RE_WITH_FLAG if with_flag else RE_SIMPLE
    seen, out = set(), []
    for slug, price, name in pattern.findall(html):
        slug  = slug.decode("utf-8")
        price = price.decode("utf-8")
        name  = name.decode("utf-8").strip()
        if slug in seen:
            continue
        seen.add(slug)
        digits = price.replace(",", "")
        out.append({
            "slug":      slug,
            "name":      name,
            "price_raw": price,
            "price":     int(digits) if digits.isdigit() else None,
        })
    return out


def main() -> int:
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)

    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Flat lookup map: { "price_dollar_rl": {...}, "sekee": {...}, ... }
    by_slug = {}
    # Grouped sections for convenience
    sections = {}

    for key, cfg in SOURCES.items():
        try:
            items = parse(fetch(cfg["url"]), cfg["flag"])
            print(f"{key}: {len(items)} items", file=sys.stderr)
        except Exception as e:
            print(f"ERROR fetching {key}: {e}", file=sys.stderr)
            items = []

        sections[key] = [it["slug"] for it in items]
        for it in items:
            by_slug[it["slug"]] = {**it, "category": key}

    payload = {
        "updated_at": updated_at,
        "source":     "https://www.tgju.org",
        "counts":     {k: len(v) for k, v in sections.items()},
        "sections":   sections,       # category -> [slug, slug, ...]
        "items":      by_slug,        # slug -> {slug, name, price, ...}
    }

    (out_dir / "prices.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
