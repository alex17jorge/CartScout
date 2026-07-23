"""Download and parse a League of Legends patch-notes page."""

import argparse
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scrape_arena import parse_arena

from scrape_champions import parse_champions
from scrape_client_game import (
    parse_buffs,
    parse_client,
    parse_game,
    parse_items,
    parse_runes,
    parse_summoner_spells,
    parse_monsters
)


PATCH_URL = "https://wiki.leagueoflegends.com/en-us/V{patch}"
HEADERS = {"User-Agent": "CartScout/1.0"}


def patch_file_stem(patch):
    if not re.fullmatch(r"\d+\.\d+", patch):
        raise ValueError("Patch must look like '26.14'.")
    return f"patch_{patch.replace('.', '_')}"


def load_patch_html(patch, raw_dir=Path("data/raw"), refresh=False):
    """Load cached patch HTML, downloading it when needed."""
    html_path = Path(raw_dir) / f"{patch_file_stem(patch)}.html"

    if refresh or not html_path.exists():
        response = requests.get(
            PATCH_URL.format(patch=patch),
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(response.text, encoding="utf-8")

    return html_path.read_text(encoding="utf-8")


def parse_patch(html, patch):
    """Parse every supported section from patch-note HTML."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "patch": patch,
        "client": parse_client(soup),
        "game": parse_game(soup),
        "champions": parse_champions(soup),
        "items": parse_items(soup),
        "runes": parse_runes(soup),
        "buffs": parse_buffs(soup),
        "summoner_spells": parse_summoner_spells(soup),
        "monsters": parse_monsters(soup),
        "aram_mayhem": parse_arena(soup, "ARAM:_Mayhem"),
        "arena": parse_arena(soup, "Arena"),
    }


def scrape_patch(
    patch,
    raw_dir=Path("data/raw"),
    output_dir=Path("data/processed"),
    refresh=False,
):
    """Load, parse, and save one patch. Return the output path."""
    html = load_patch_html(patch, raw_dir, refresh)
    patch_data = parse_patch(html, patch)
    output_path = Path(output_dir) / f"{patch_file_stem(patch)}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(patch_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patch", help="Patch number, for example 26.14")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download the page even when a cached HTML file exists",
    )
    args = parser.parse_args()

    output_path = scrape_patch(args.patch, refresh=args.refresh)
    print(f"Saved JSON to: {output_path}")


if __name__ == "__main__":
    main()
