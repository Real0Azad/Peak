#!/usr/bin/env python3

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
    "currencies": "https://www.tgju.org/currency",
    "coins":      "https://www.tgju.org/coin",
    "gold":       "https://www.tgju.org/gold-chart",
}

RE_SLUG  = re.compile(rb'data-market-nameslug="([^"]+)"')
RE_PRICE = re.compile(rb'data-price="([^"]*)"')
RE_TH    = re.compile(rb'<th[^>]*>(.*?)</th>', re.DOTALL)
RE_TAGS  = re.compile(rb'<[^>]+>')


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.status


def iter_tr(html: bytes):
    """Yield (attrs_bytes, content_bytes) for each <tr ...>...</tr>.

    Walks the tag boundary with a tiny state machine so a `>` inside a
    quoted attribute value (e.g. data-title="<div ...>") does not break
    the split.
    """
    n = len(html)
    i = 0
    while True:
        i = html.find(b'<tr', i)
        if i == -1:
            return
        j = i + 3
        # skip <truename...> like <track>; require space, /, >, or EOL after "tr"
        if j < n and html[j] not in b' \t\r\n>/':
            i = j
            continue

        # find the '>' that closes the opening tag, ignoring those inside "..."
        k = j
        in_q = False
        while k < n:
            c = html[k]
            if in_q:
                if c == 0x22:      # closing "
                    in_q = False
            else:
                if c == 0x22:      # opening "
                    in_q = True
                elif c == 0x3e:    # >
                    break
            k += 1
        if k >= n:
            return

        attrs = html[j:k]
        end   = html.find(b'</tr>', k)
        if end == -1:
            return
        content = html[k + 1:end]

        yield attrs, content
        i = end + 5


def parse(html: bytes):
    items, seen = [], set()
    for attrs, content in iter_tr(html):
        if b'data-market-nameslug' not in attrs:
            continue

        slug_m  = RE_SLUG.search(attrs)
        price_m = RE_PRICE.search(attrs)
        th_m    = RE_TH.search(content)
        if not (slug_m and price_m and th_m):
            continue

        slug  = slug_m.group(1).decode("utf-8", "replace")
        price = price_m.group(1).decode("utf-8", "replace")
        name  = RE_TAGS.sub(b"", th_m.group(1)).decode("utf-8", "replace").strip()

        if not name or slug in seen:
            continue
        seen.add(slug)

        digits = price.replace(",", "")
        items.append({
            "slug":      slug,
            "name":      name,
            "price_raw": price,
            "price":     int(digits) if digits.isdigit() else None,
        })
    return items


def main():
    debug   = "--debug" in sys.argv
    out_dir = Path("data")
    dbg_dir = Path("debug")
    out_dir.mkdir(exist_ok=True)

    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    by_slug, sections = {}, {}

    for key, url in SOURCES.items():
        try:
            html, status = fetch(url)
            items = parse(html)
            print(f"{key}: HTTP {status}, {len(html)} bytes, {len(items)} items",
                  file=sys.stderr)

            if debug:
                dbg_dir.mkdir(exist_ok=True)
                (dbg_dir / f"{key}.html").write_bytes(html)

            if not items:
                # Diagnostics — tells us if the data is even in the response.
                n_tr    = html.count(b"<tr")
                n_slug  = html.count(b"data-market-nameslug")
                n_price = html.count(b"data-price")
                head    = html[:200].decode("utf-8", "replace").replace("\n", " ")
                print(f"   diag: <tr={n_tr}, slug={n_slug}, price={n_price}, "
                      f"head={head!r}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR {key}: {e!r}", file=sys.stderr)
            items = []

        sections[key] = [it["slug"] for it in items]
        for it in items:
            by_slug[it["slug"]] = {**it, "category": key}

    payload = {
        "updated_at": updated_at,
        "counts":     {k: len(v) for k, v in sections.items()},
        "sections":   sections,
        "items":      by_slug,
    }
    (out_dir / "prices.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
