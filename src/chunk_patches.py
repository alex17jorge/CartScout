import json
import re
from pathlib import Path

INPUT_DIR = Path("data/processed")
OUTPUT_PATH = Path("data/chunks/patch_chunks.jsonl")

MAX_CHUNK_CHARACTERS = 1600

#convert a name into an ID component
def slugify(value):
    text = str(value)
    lowercase_text = text.lower()
    trimmed_text = lowercase_text.strip()

    slug = re.sub(r"[^a-z0-9]+", "-", trimmed_text)
    slug = slug.strip("-")

    if slug == "":
        return "general"

    return slug


#keeps each change sentence intact, if an entity is too large, it creates multiple chunks and repeats header
def split_changes(header_lines, changes, max_characters=MAX_CHUNK_CHARACTERS):
    cleaned_changes = []

    for change in changes:
        cleaned_change = str(change).strip()

        if cleaned_change:
            cleaned_changes.append(cleaned_change)

    if not cleaned_changes:
        return []

    header_text = "\n".join(header_lines)
    changes_heading = "\nChanges:\n"
    header_size = len(header_text) + len(changes_heading)

    batches = []
    current_batch = []
    current_size = header_size

    for change in cleaned_changes:
        bullet = f"- {change}"
        newline_size = 1
        change_size = len(bullet) + newline_size

        would_be_too_large = (
            current_size + change_size > max_characters
        )

        if current_batch and would_be_too_large:
            batches.append(current_batch)

            current_batch = []
            current_size = header_size

        current_batch.append(change)
        current_size += change_size

    if current_batch:
        batches.append(current_batch)

    return batches


def make_chunks(
    patch,
    section,
    entity,
    entity_label,
    changes,
    source,
    record_id,
    category=None,
    game_mode=None,
):
    section_name = section.replace("_", " ").title()

    header_lines = [
        f"Patch: {patch}",
        f"Section: {section_name}",
    ]

    if game_mode:
        header_lines.append(f"Game mode: {game_mode}")

    if category:
        header_lines.append(f"Category: {category}")

    entity_header = f"{entity_label}: {entity}"
    header_lines.append(entity_header)

    change_batches = split_changes(
        header_lines,
        changes,
    )

    chunks = []

    entity_slug = slugify(entity)

    parent_id = f"{patch}|{section}|{entity_slug}"

    part_number = 1

    for batch in change_batches:
        content_lines = header_lines.copy()
        content_lines.append("Changes:")

        for change in batch:
            bullet = f"- {change}"
            content_lines.append(bullet)

        content = "\n".join(content_lines)

        category_name = category or "general"
        category_slug = slugify(category_name)

        chunk_id = (
            f"{patch}|{section}|{record_id}|"
            f"{entity_slug}|{category_slug}|{part_number}"
        )

        metadata = {
            "patch": patch,
            "section": section,
            "entity": entity,
            "source": source,
            "parent_id": parent_id,
            "part": part_number,
        }

        if category:
            metadata["category"] = category

        if game_mode:
            metadata["game_mode"] = game_mode

        chunk = {
            "id": chunk_id,
            "content": content,
            "metadata": metadata,
        }

        chunks.append(chunk)

        part_number += 1

    return chunks


FLAT_SECTIONS = {
    "items": "Item",
    "runes": "Rune",
    "buffs": "Buff",
    "summoner_spells": "Summoner spell",
    "monsters": "Monster",
    "client": "Client entry",
    "game": "Game entry",
}


def chunk_flat_sections(data, patch, source):
    all_chunks = []

    for section_name in FLAT_SECTIONS:
        entity_label = FLAT_SECTIONS[section_name]

        entries = data.get(section_name, [])

        for entry_index in range(len(entries)):
            entry = entries[entry_index]

            name = entry.get("name")
            changes = entry.get("changes", [])

            has_no_name = not name
            has_no_changes = not changes

            if has_no_name or has_no_changes:
                continue

            entry_chunks = make_chunks(
                patch=patch,
                section=section_name,
                entity=name,
                entity_label=entity_label,
                changes=changes,
                source=source,
                record_id=entry_index,
            )

            all_chunks.extend(entry_chunks)

    return all_chunks


def chunk_champions(data, patch, source):
    all_chunks = []

    champions = data.get("champions", [])

    for champion_index in range(len(champions)):
        champion = champions[champion_index]
        champion_name = champion.get("name")

        if not champion_name:
            continue

        champion_changes = champion.get("changes", [])

        for change_index in range(len(champion_changes)):
            change = champion_changes[change_index]

            ability = change.get("ability")

            if not ability:
                ability = change.get("category")

            if not ability:
                ability = "General"

            details = change.get("details", [])

            if not details:
                continue

            record_id = f"{champion_index}-{change_index}"

            ability_chunks = make_chunks(
                patch=patch,
                section="champions",
                entity=champion_name,
                entity_label="Champion",
                category=ability,
                changes=details,
                source=source,
                record_id=record_id,
            )

            all_chunks.extend(ability_chunks)

    return all_chunks


GAME_MODE_SECTIONS = {
    "arena": "Arena",
    "aram_mayhem": "ARAM: Mayhem",
}


def chunk_game_modes(data, patch, source):
    all_chunks = []

    for section_name in GAME_MODE_SECTIONS:
        game_mode_name = GAME_MODE_SECTIONS[section_name]

        groups = data.get(section_name, [])

        for group_index, group in enumerate(groups):
            group_category = group.get("category")
            entries = group.get("entries", [])

            for entry_index, entry in enumerate(entries):
                entry_name = entry.get("name")
                changes = entry.get("changes", [])

                entry_category = group_category

                if not entry_name and group_category:
                    entry_name = group_category
                    entry_category = None

                if not entry_name:
                    entry_name = "General"

                if not changes:
                    continue

                record_id = f"{group_index}-{entry_index}"

                entry_chunks = make_chunks(
                    patch=patch,
                    section=section_name,
                    entity=entry_name,
                    entity_label="Entry",
                    category=entry_category,
                    game_mode=game_mode_name,
                    changes=changes,
                    source=source,
                    record_id=record_id,
                )

                all_chunks.extend(entry_chunks)

    return all_chunks


def chunk_patch(data, source):
    patch_value = data.get("patch", "")
    patch = str(patch_value).strip()

    if not patch:
        error_message = f"Missing patch number in {source}"
        raise ValueError(error_message)

    all_chunks = []

    flat_section_chunks = chunk_flat_sections(
        data,
        patch,
        source,
    )
    all_chunks.extend(flat_section_chunks)

    champion_chunks = chunk_champions(
        data,
        patch,
        source,
    )
    all_chunks.extend(champion_chunks)

    game_mode_chunks = chunk_game_modes(
        data,
        patch,
        source,
    )
    all_chunks.extend(game_mode_chunks)

    return all_chunks


def main():
    all_chunks = []

    input_paths = list(INPUT_DIR.glob("patch_*.json"))
    input_paths.sort()

    if len(input_paths) == 0:
        error_message = f"No patch JSON files found in {INPUT_DIR}"
        raise FileNotFoundError(error_message)

    for input_path in input_paths:
        file_text = input_path.read_text(encoding="utf-8")
        data = json.loads(file_text)

        patch_chunks = chunk_patch(
            data=data,
            source=input_path.as_posix(),
        )

        all_chunks.extend(patch_chunks)

        file_name = input_path.name
        number_of_chunks = len(patch_chunks)

        print(
            f"{file_name}: created {number_of_chunks} chunks"
        )

    output_folder = OUTPUT_PATH.parent

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open("w", encoding="utf-8") as output_file:
        for chunk in all_chunks:
            chunk_json = json.dumps(
                chunk,
                ensure_ascii=False,
            )

            output_file.write(chunk_json)
            output_file.write("\n")

    total_chunks = len(all_chunks)

    print(f"Total chunks: {total_chunks}")
    print(f"Saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()