from scrape_common import parse_plain_named_section
from scrape_common import parse_named_section


def parse_client(soup):
    return parse_plain_named_section(soup, "Client")

def parse_game(soup):
    return parse_plain_named_section(soup, "Game")


def parse_summoner_spells(soup):
    return parse_plain_named_section(soup, "Summoner_Spells")

def parse_items(soup):
    return parse_named_section(
        soup,
        "Items",
        "item-icon",
        "data-item",
        allow_plain_names=True,
        allow_multiple_names=True,
    )

def parse_runes(soup):
    return parse_named_section(soup, "Runes", "rune-icon", "data-rune")

def parse_buffs(soup):
    return parse_named_section(soup, "Neutral_buffs", "buff-icon", "data-buff")

def parse_monsters(soup):
    return parse_plain_named_section(soup, "Monsters")
