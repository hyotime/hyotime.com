#!/usr/bin/env python3
"""Refresh the homepage 글 cards from the public Naver RSS feed.

Only the region between BLOG-CARDS:BEGIN and BLOG-CARDS:END in index.html
is rewritten. A failed fetch or an empty feed leaves the file untouched.
"""

from __future__ import annotations

import html
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

RSS_URL = "https://rss.blog.naver.com/compoundays.xml"
USER_AGENT = (
    "Mozilla/5.0 (compatible; hyotime-blog-sync/1.0; +https://www.hyotime.com/)"
)
MAX_POSTS = 6
ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
BEGIN = "<!-- BLOG-CARDS:BEGIN -->"
END = "<!-- BLOG-CARDS:END -->"


def fetch_rss(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"RSS HTTP {status}")
        return response.read()


def clean_link(item: ET.Element) -> str | None:
    guid = (item.findtext("guid") or "").strip()
    link = (item.findtext("link") or "").strip()
    url = (guid or link).split("?", 1)[0].strip()
    if not url.startswith("https://blog.naver.com/compoundays/"):
        return None
    return url


def parse_items(payload: bytes) -> list[dict]:
    root = ET.fromstring(payload)
    parsed = []
    for item in root.findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split())
        category = " ".join((item.findtext("category") or "").split())
        link = clean_link(item)
        published = (item.findtext("pubDate") or "").strip()
        if not title or not link or not published:
            continue
        when = parsedate_to_datetime(published)
        if when is None:
            continue
        parsed.append(
            {"title": title, "category": category, "link": link, "when": when}
        )
    parsed.sort(key=lambda entry: entry["when"], reverse=True)
    unique = []
    seen = set()
    for entry in parsed:
        if entry["link"] in seen:
            continue
        seen.add(entry["link"])
        unique.append(entry)
        if len(unique) == MAX_POSTS:
            break
    return unique


def esc_text(value: str) -> str:
    return html.escape(value, quote=False)


def esc_attr(value: str) -> str:
    return html.escape(value, quote=True)


def render_cards(items: list[dict]) -> str:
    lines = ["      <div class=\"post-grid\">"]
    for entry in items:
        when = entry["when"]
        lines.append(
            "        <a class=\"post-card\" "
            f"href=\"{esc_attr(entry['link'])}\" "
            "target=\"_blank\" rel=\"noopener noreferrer\">"
        )
        if entry["category"]:
            lines.append(
                f"          <p class=\"post-cat\">{esc_text(entry['category'])}</p>"
            )
        lines.append(
            f"          <h3 class=\"post-title\">{esc_text(entry['title'])}</h3>"
        )
        lines.append(
            "          <time class=\"post-date\" "
            f"datetime=\"{when.strftime('%Y-%m-%d')}\">"
            f"{when.strftime('%Y.%m.%d')}</time>"
        )
        lines.append("        </a>")
    lines.append("      </div>")
    return "\n".join(lines)


def replace_region(source: str, cards: str) -> str:
    start = source.find(BEGIN)
    end = source.find(END)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("blog card markers are missing from index.html")
    end_close = end + len(END)
    block = f"{BEGIN}\n{cards}\n      {END}"
    return source[:start] + block + source[end_close:]


def main() -> int:
    try:
        payload = fetch_rss(RSS_URL)
        items = parse_items(payload)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, RuntimeError, ValueError) as exc:
        print(f"RSS sync skipped: {exc}", file=sys.stderr)
        return 1
    if not items:
        print("RSS sync skipped: feed returned no posts", file=sys.stderr)
        return 1
    original = INDEX.read_text(encoding="utf-8")
    updated = replace_region(original, render_cards(items))
    if updated == original:
        print(f"Blog cards already match the latest {len(items)} post(s).")
        return 0
    INDEX.write_text(updated, encoding="utf-8")
    print(f"Updated blog cards ({len(items)} post(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
