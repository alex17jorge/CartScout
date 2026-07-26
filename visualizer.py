"""Display Chroma embeddings as a simple 2D scatter plot."""

import argparse
import tkinter as tk
from pathlib import Path

import chromadb
import numpy as np


CHROMA_PATH = Path("data/chroma_large")
COLLECTION_NAME = "cartscout-patches-v1"

SECTION_COLORS = {
    "champions": "#4f8cff",
    "items": "#f59e0b",
    "runes": "#a855f7",
    "buffs": "#22c55e",
    "summoner_spells": "#06b6d4",
    "monsters": "#ef4444",
    "client": "#64748b",
    "game": "#14b8a6",
    "arena": "#ec4899",
    "aram_mayhem": "#8b5cf6",
}


def load_embeddings():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
    )
    result = collection.get(
        limit=collection.count(),
        include=["embeddings", "metadatas"],
    )

    embeddings = result["embeddings"]
    if embeddings is None or len(embeddings) < 2:
        raise ValueError("At least two embeddings are required.")

    return (
        np.asarray(embeddings, dtype=np.float64),
        result["metadatas"] or [{}] * len(embeddings),
    )


def project_to_2d(embeddings):
    """Normalize the vectors and project them to two dimensions with PCA."""
    lengths = np.linalg.norm(embeddings, axis=1, keepdims=True)
    lengths[lengths == 0] = 1
    normalized = embeddings / lengths
    centered = normalized - normalized.mean(axis=0, keepdims=True)

    # Use the smaller sample-space matrix instead of a 1536x1536 matrix.
    gram_matrix = centered @ centered.T
    eigenvalues, eigenvectors = np.linalg.eigh(gram_matrix)
    order = np.argsort(eigenvalues)[::-1]
    top_values = np.maximum(eigenvalues[order[:2]], 0)

    return eigenvectors[:, order[:2]] * np.sqrt(top_values)


def draw_graph(canvas, coordinates, sections):
    canvas.delete("all")

    width = max(canvas.winfo_width(), 100)
    height = max(canvas.winfo_height(), 100)
    left = 55
    right = 25
    top = 25
    bottom = 45

    minimums = coordinates.min(axis=0)
    ranges = coordinates.max(axis=0) - minimums
    ranges[ranges == 0] = 1
    scaled = (coordinates - minimums) / ranges

    canvas.create_line(
        left, height - bottom, width - right, height - bottom,
        fill="#94a3b8",
    )
    canvas.create_line(
        left, top, left, height - bottom,
        fill="#94a3b8",
    )
    canvas.create_text(
        (left + width - right) / 2,
        height - 15,
        text="PCA component 1",
        fill="#cbd5e1",
    )
    canvas.create_text(
        15,
        (top + height - bottom) / 2,
        text="PCA component 2",
        fill="#cbd5e1",
        angle=90,
    )

    plot_width = width - left - right
    plot_height = height - top - bottom

    for index, point in enumerate(scaled):
        section = sections[index]
        x = left + point[0] * plot_width
        y = height - bottom - point[1] * plot_height
        radius = 4

        canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=SECTION_COLORS.get(section, "#94a3b8"),
            outline="",
        )


def create_window(coordinates, sections):
    root = tk.Tk()
    root.title("CartScout embedding vectors")
    root.geometry("1100x700")
    root.minsize(700, 450)

    canvas = tk.Canvas(
        root,
        background="#0b1120",
        highlightthickness=0,
    )
    canvas.pack(side="left", fill="both", expand=True)

    legend = tk.Frame(root, background="#111827", padx=18, pady=18)
    legend.pack(side="right", fill="y")

    tk.Label(
        legend,
        text="Section",
        background="#111827",
        foreground="#e5e7eb",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    for section in sorted(set(sections)):
        row = tk.Frame(legend, background="#111827")
        row.pack(anchor="w", pady=3)

        swatch = tk.Canvas(
            row,
            width=12,
            height=12,
            background="#111827",
            highlightthickness=0,
        )
        swatch.create_oval(
            2,
            2,
            10,
            10,
            fill=SECTION_COLORS.get(section, "#94a3b8"),
            outline="",
        )
        swatch.pack(side="left", padx=(0, 7))

        tk.Label(
            row,
            text=section.replace("_", " "),
            background="#111827",
            foreground="#d1d5db",
        ).pack(side="left")

    canvas.bind(
        "<Configure>",
        lambda _event: draw_graph(canvas, coordinates, sections),
    )
    draw_graph(canvas, coordinates, sections)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the vectors without opening the graph",
    )
    args = parser.parse_args()

    embeddings, metadatas = load_embeddings()
    coordinates = project_to_2d(embeddings)
    sections = [
        str((metadata or {}).get("section", "unknown"))
        for metadata in metadatas
    ]

    if args.check:
        print(f"Loaded {len(embeddings)} vectors")
        return

    create_window(coordinates, sections)


if __name__ == "__main__":
    main()
