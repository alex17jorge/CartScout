import json
import re
from pathlib import Path

INPUT_DIR = Path("data/processed")
OUTPUT_PATH = Path("data/chunks/patch_chunks.jsonl")

MAX_CHUNK_CHARACTERS = 1600

#convert a name into an ID component
def slugify(value):
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value) #replace any character that is not lowercase into an enhyphen -
    return value.strip("-") or "general"


#keeps each change sentence intact, if an entity is too large, it creates multiple chunks and repeats header
def split_changes(header_lines, changes, max_characters=MAX_CHUNK_CHARACTERS):
    changes = [
        str(change).strip()

        for change in changes
        if str(change).strip()
    ]

    if not changes:
        return []

    header_size = len("\n".join(header_lines)) + len("\nChanges:\n")
    batches = []
    current_batch = []
    current_size = header_size

    for change in changes:
        bullet = f"- {change}"
        additional_size = len(bullet) + 1

        if current_batch and current_size + additional_size > max_characters:
            batches.append(current_batch)
            current_batch = []
            current_size = header_size

        current_batch.append(change)
        current_size += additional_size

    if current_batch:
        batches.append(current_batch)

    return batches


def make_chunks(patch, section, entity, entity_label, changes, source, record_id, category=None, game_mode=None):
    section_name = section.replace("_", " ").title()

    header_lines = [
        f"Patch: {patch}",
        f"Section: {section_name}"
    ]

    if game_mode:
        header_lines.append(f"Game mode: {game_mode}")

    if category:
        header_lines.append(f"Category: {category}")

    header_lines.append(f"{entity_label}: {entity}")

    change_batches = split_changes(header_lines, changes)
    chunks = []

    parent_id = "|".join(
        [
            patch,
            section,
            slugify(entity),
        ]
    )

    for part_number, batch in enumerate(change_batches, start=1):
        content = "\n".join(
            [
                *header_lines,
                "Changes:",
                *(f"- {change}" for change in batch),
            ]
        )

        chunk_id = "|".join(
            [
                patch,
                section,
                str(record_id),
                slugify(entity),
                slugify(category or "general"),
                str(part_number),
            ]
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

        chunks.append(
            {
                "id": chunk_id,
                "content": content,
                "metadata": metadata,
            }
        )

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
    chunks = []

    for section, entity_label in FLAT_SECTIONS.items():
        entries = data.get(section, [])

        for entry_index, entry in enumerate(entries):
            name = entry.get("name")
            changes = entry.get("changes", [])

            if not name or not changes:
                continue

            chunks.extend(
                make_chunks(
                    patch=patch,
                    section=section,
                    entity=name,
                    entity_label=entity_label,
                    changes=changes,
                    source=source,
                    record_id=entry_index,
                )
            )

    return chunks


def chunk_champions(data, patch, source):
    chunks = []

    for champion_index, champion in enumerate(data.get("champions", [])):
        champion_name = champion.get("name")

        if not champion_name:
            continue

        for change_index, change in enumerate(champion.get("changes", [])):
            # Supports both names in case older JSON used "category".
            ability = (
                change.get("ability")
                or change.get("category")
                or "General"
            )

            details = change.get("details", [])

            if not details:
                continue

            chunks.extend(
                make_chunks(
                    patch=patch,
                    section="champions",
                    entity=champion_name,
                    entity_label="Champion",
                    category=ability,
                    changes=details,
                    source=source,
                    record_id=f"{champion_index}-{change_index}",
                )
            )

    return chunks


GAME_MODE_SECTIONS = {
    "arena": "Arena",
    "aram_mayhem": "ARAM: Mayhem",
}


def chunk_game_modes(data, patch, source):
    chunks = []

    for section, game_mode in GAME_MODE_SECTIONS.items():
        groups = data.get(section, [])

        for group_index, group in enumerate(groups):
            category = group.get("category")

            for entry_index, entry in enumerate(group.get("entries", [])):
                entry_name = entry.get("name")
                changes = entry.get("changes", [])

                # Also handles older ARAM data where the champion name
                # was incorrectly placed in category.
                if not entry_name and category:
                    entry_name = category
                    entry_category = None
                else:
                    entry_category = category

                if not entry_name:
                    entry_name = "General"

                if not changes:
                    continue

                chunks.extend(
                    make_chunks(
                        patch=patch,
                        section=section,
                        entity=entry_name,
                        entity_label="Entry",
                        category=entry_category,
                        game_mode=game_mode,
                        changes=changes,
                        source=source,
                        record_id=f"{group_index}-{entry_index}",
                    )
                )

    return chunks


def chunk_patch(data, source):
    patch = str(data.get("patch", "")).strip()

    if not patch:
        raise ValueError(f"Missing patch number in {source}")

    chunks = []
    chunks.extend(chunk_flat_sections(data, patch, source))
    chunks.extend(chunk_champions(data, patch, source))
    chunks.extend(chunk_game_modes(data, patch, source))

    return chunks


def main():
    all_chunks = []

    input_paths = sorted(INPUT_DIR.glob("patch_*.json"))

    if not input_paths:
        raise FileNotFoundError(
            f"No patch JSON files found in {INPUT_DIR}"
        )

    for input_path in input_paths:
        data = json.loads(input_path.read_text(encoding="utf-8"))

        patch_chunks = chunk_patch(
            data=data,
            source=input_path.as_posix(),
        )

        all_chunks.extend(patch_chunks)

        print(
            f"{input_path.name}: "
            f"created {len(patch_chunks)} chunks"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as output_file:
        for chunk in all_chunks:
            output_file.write(
                json.dumps(chunk, ensure_ascii=False) + "\n"
            )

    print(f"Total chunks: {len(all_chunks)}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()