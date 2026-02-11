#!/usr/bin/env python3
"""Update Google Scholar citations in _data/scholar.yml."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import yaml


def load_scholar_url(config_path: Path) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    author = config.get("author") or {}
    scholar_url = author.get("googlescholar")
    if not scholar_url:
        raise ValueError(f"Missing author.googlescholar in {config_path}")
    return str(scholar_url).strip()


def extract_user_id(scholar_url: str) -> str:
    parsed = urlparse(scholar_url)
    user = parse_qs(parsed.query).get("user", [None])[0]
    if not user:
        raise ValueError(f"Cannot find 'user' parameter in Google Scholar URL: {scholar_url}")
    return user


def fetch_profile_html(user_id: str, timeout: int = 20) -> str:
    url = f"https://scholar.google.com/citations?hl=en&user={user_id}"
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_total_citations(html: str) -> int:
    table_match = re.search(r'<table[^>]*id="gsc_rsb_st"[^>]*>(.*?)</table>', html, re.S)
    if table_match:
        values = re.findall(r'class="gsc_rsb_std">([0-9,]+)<', table_match.group(1))
        if values:
            return int(values[0].replace(",", ""))

    fallback = re.search(r'>Cited by ([0-9,]+)<', html)
    if fallback:
        return int(fallback.group(1).replace(",", ""))

    raise RuntimeError("Failed to parse citation count from Google Scholar HTML.")


def load_existing_citations(data_path: Path) -> int | None:
    if not data_path.exists():
        return None
    data = yaml.safe_load(data_path.read_text(encoding="utf-8")) or {}
    value = data.get("citations")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_data(data_path: Path, citations: int, profile_url: str, user_id: str) -> None:
    payload = {
        "citations": citations,
        "profile_url": profile_url,
        "user_id": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="_config.yml", help="Path to Jekyll _config.yml")
    parser.add_argument("--output", default="_data/scholar.yml", help="Output data file path")
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)

    previous_citations = load_existing_citations(output_path)
    scholar_url = load_scholar_url(config_path)
    user_id = extract_user_id(scholar_url)

    try:
        html = fetch_profile_html(user_id)
        citations = parse_total_citations(html)
    except Exception as exc:  # noqa: BLE001
        if previous_citations is not None:
            print(
                "Warning: failed to refresh Google Scholar citations "
                f"({exc}). Keeping existing value: {previous_citations}"
            )
            return 0
        raise

    if previous_citations == citations:
        print(f"No citation change. Current citations: {citations}")
        return 0

    write_data(output_path, citations, scholar_url, user_id)
    print(f"Updated citations: {previous_citations} -> {citations}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
