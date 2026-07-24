import json
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

CHUNKS_PATH = Path("data/chunks/patch_chunks.jsonl")
CHROMA_PATH = Path("data/chroma")

COLLECTION_NAME = "cartscout-patches-v1"
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 64


def load_chunks(path):
    chunks = []

    with path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()

            if not line:
                continue

            chunk = json.loads(line)

            if not chunk.get("id"):
                raise ValueError(
                    f"Missing chunk ID on line {line_number}"
                )

            if not chunk.get("content"):
                raise ValueError(
                    f"Missing chunk content on line {line_number}"
                )

            chunks.append(chunk)

    return chunks


def create_batches(items, batch_size):
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def clean_metadata(metadata):
    allowed_types = (str, int, float, bool)

    return {
        key: value
        for key, value in metadata.items()
        if value is not None
        and isinstance(value, allowed_types)
    }


def create_embeddings(openai_client, texts):
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        encoding_format="float",
    )

    embedding_results = sorted(
        response.data,
        key=lambda result: result.index,
    )

    return [
        result.embedding
        for result in embedding_results
    ]


def store_batch(collection, batch, embeddings):
    ids = []
    documents = []
    metadatas = []

    for chunk in batch:
        ids.append(chunk["id"])
        documents.append(chunk["content"])
        metadatas.append(
            clean_metadata(chunk.get("metadata", {}))
        )

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def main():
    load_dotenv()

    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            f"Chunk file not found: {CHUNKS_PATH}"
        )

    chunks = load_chunks(CHUNKS_PATH)

    if not chunks:
        raise ValueError("The chunk file contains no chunks.")

    print(f"Loaded {len(chunks)} chunks")

    openai_client = OpenAI()

    chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_PATH)
    )

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        metadata={
            "embedding_model": EMBEDDING_MODEL,
            "description": "League of Legends patch-note chunks",
        },
    )

    processed = 0

    for batch_number, batch in enumerate(
        create_batches(chunks, BATCH_SIZE),
        start=1,
    ):
        texts = [
            chunk["content"]
            for chunk in batch
        ]

        embeddings = create_embeddings(
            openai_client,
            texts,
        )

        if len(embeddings) != len(batch):
            raise RuntimeError(
                "The number of embeddings does not match "
                "the number of chunks."
            )

        store_batch(
            collection=collection,
            batch=batch,
            embeddings=embeddings,
        )

        processed += len(batch)

        print(
            f"Batch {batch_number}: "
            f"stored {processed}/{len(chunks)} chunks"
        )

    print(f"Collection records: {collection.count()}")
    print(f"Chroma database: {CHROMA_PATH}")
    print(f"Collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()