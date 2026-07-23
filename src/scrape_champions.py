from scrape_common import direct_text, iter_section_elements, list_item_texts


def parse_champions(soup):
    champions = []

    for element in iter_section_elements(soup, "Champions"):
        icon = element.select_one("dt span.champion-icon[data-champion]")
        if not icon:
            continue

        champion = {
            "name": icon.get("data-champion"),
            "changes": [],
        }
        change_list = element.find_next_sibling("ul")

        if change_list:
            for item in change_list.find_all("li", recursive=False):
                details_list = item.find("ul", recursive=False)
                champion["changes"].append(
                    {
                        "ability": direct_text(item, details_list) if details_list else None,
                        "details": (
                            list_item_texts(details_list)
                            if details_list
                            else [item.get_text(" ", strip=True)]
                        ),
                    }
                )

        champions.append(champion)

    return champions
