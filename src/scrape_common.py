"""Shared helpers for parsing League of Legends patch-note sections."""


def iter_section_elements(soup, section_id):
    """Yield siblings in an h3 section, stopping at the next h3 section."""
    heading = soup.find("h3", id=section_id)
    if not heading or not heading.parent:
        return

    current = heading.parent.find_next_sibling()
    while current and not current.find("h3"):
        yield current
        current = current.find_next_sibling()


def direct_text(element, nested_element):
    """Return an element's text without mutating it or including a nested list."""
    full_text = element.get_text(" ", strip=True)
    nested_text = nested_element.get_text(" ", strip=True)
    return full_text.replace(nested_text, "", 1).strip()


def list_item_texts(list_element):
    """Return the text of the direct li children of a list."""
    return [
        text
        for item in list_element.find_all("li", recursive=False)
        if (text := item.get_text(" ", strip=True))
    ]


def flattened_changes(list_element):
    """Flatten top-level and one-level nested changes without altering the soup."""
    changes = []

    for item in list_element.find_all("li", recursive=False):
        nested_list = item.find("ul", recursive=False)
        text = (
            direct_text(item, nested_list)
            if nested_list
            else item.get_text(" ", strip=True)
        )

        if text:
            changes.append(text)
        if nested_list:
            changes.extend(list_item_texts(nested_list))

    return changes


def parse_named_section(
    soup,
    section_id,
    icon_class=None,
    data_attribute=None,
    allow_plain_names=False,
    allow_multiple_names=False,
):
    """Parse a section made up of a named icon followed by a change list."""
    entries = []

    for element in iter_section_elements(soup, section_id):
        icons = (
            element.select(f"dt span.{icon_class}[{data_attribute}]")
            if icon_class and data_attribute
            else []
        )
        if not allow_multiple_names:
            icons = icons[:1]

        names = [
            name
            for icon in icons
            if (name := icon.get(data_attribute))
        ]

        if not names and allow_plain_names:
            name_element = element.find("dt")
            name = name_element.get_text(" ", strip=True) if name_element else None
            names = [name] if name else []

        if not names:
            continue

        change_list = element.find_next_sibling("ul")
        changes = flattened_changes(change_list) if change_list else []
        entries.extend(
            {"name": name, "changes": changes.copy()}
            for name in dict.fromkeys(names)
        )

    return entries


def parse_plain_named_section(soup, section_id):
    """Parse entries whose names are plain text inside dt elements."""
    return parse_named_section(soup, section_id, allow_plain_names=True)
