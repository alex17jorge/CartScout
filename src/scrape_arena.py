from scrape_common import direct_text, iter_section_elements, list_item_texts


def parse_arena(soup, section_id):
    categories = []

    for element in iter_section_elements(soup, section_id):
        if element.name != "ul":
            continue

        for category_element in element.find_all("li", recursive=False):
            entry_list = category_element.find("ul", recursive=False)
            if not entry_list:
                continue

            entry_elements = entry_list.find_all("li", recursive=False)
            has_named_entries = any(
                entry.find("ul", recursive=False) for entry in entry_elements
            )

            if not has_named_entries:
                categories.append(
                    {
                        "category": None,
                        "entries": [
                            {
                                "name": direct_text(category_element, entry_list),
                                "changes": list_item_texts(entry_list),
                            }
                        ],
                    }
                )
                continue

            category = {
                "category": direct_text(category_element, entry_list),
                "entries": [],
            }

            for entry_element in entry_elements:
                changes_list = entry_element.find("ul", recursive=False)
                category["entries"].append(
                    {
                        "name": (
                            direct_text(entry_element, changes_list)
                            if changes_list
                            else None
                        ),
                        "changes": (
                            list_item_texts(changes_list)
                            if changes_list
                            else [entry_element.get_text(" ", strip=True)]
                        ),
                    }
                )

            categories.append(category)

    return categories
