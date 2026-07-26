import json
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

CHUNKS_PATH = Path("data/chunks/patch_chunks.jsonl")
CHROMA_PATH = Path("data/chroma")
CHROMA_PATH_LARGE = Path("data/chroma_large")

COLLECTION_NAME = "cartscout-patches-v1"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_MODEL_LARGE = "text-embedding-3-large"
BATCH_SIZE = 64


def load_chunks(path):
    loaded_chunks = []

    with path.open("r", encoding="utf-8") as input_file:
        line_number = 0

        for line in input_file:
            line_number += 1

            cleaned_line = line.strip()

            if not cleaned_line:
                continue

            chunk = json.loads(cleaned_line)

            chunk_id = chunk.get("id")
            chunk_content = chunk.get("content")

            if not chunk_id:
                raise ValueError(
                    f"Missing chunk ID on line {line_number}"
                )

            if not chunk_content:
                raise ValueError(
                    f"Missing chunk content on line {line_number}"
                )

            loaded_chunks.append(chunk)

    return loaded_chunks



def create_batches(items, batch_size):
    number_of_items = len(items)

    for start_index in range(0, number_of_items, batch_size):
        end_index = start_index + batch_size
        batch = items[start_index:end_index]

        yield batch

def clean_metadata(metadata):
    allowed_types = (str,int,float,bool)

    cleaned_metadata = {}

    for key, value in metadata.items():
        value_is_not_none = value is not None
        value_has_allowed_type = isinstance(value, allowed_types)

        if value_is_not_none and value_has_allowed_type:
            cleaned_metadata[key] = value

    return cleaned_metadata


def create_embeddings(openai_client, texts):
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL_LARGE,
        input=texts,
        encoding_format="float",
    )

    embedding_results = response.data

    embedding_results = sorted(embedding_results,key=lambda result: result.index)

    embeddings = []

    for result in embedding_results:
        embeddings.append(result.embedding)

    return embeddings

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
        error_message = f"Chunk file not found: {CHUNKS_PATH}"
        raise FileNotFoundError(error_message)

    chunks = load_chunks(CHUNKS_PATH)

    if not chunks:
        raise ValueError("The chunk file contains no chunks.")

    total_chunks = len(chunks)
    print(f"Loaded {total_chunks} chunks")

    openai_client = OpenAI()

    chroma_path_text = str(CHROMA_PATH_LARGE)

    chroma_client = chromadb.PersistentClient(
        path=chroma_path_text
    )

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        metadata={
            "embedding_model": EMBEDDING_MODEL_LARGE,
            "description": "League of Legends patch-note chunks",
        },
    )

    processed_chunks = 0

    batches = create_batches(
        chunks,
        BATCH_SIZE,
    )

    for batch_number, batch in enumerate(batches, start=1):
        texts = []

        for chunk in batch:
            texts.append(chunk["content"])

        embeddings = create_embeddings(
            openai_client,
            texts,
        )

        number_of_embeddings = len(embeddings)
        number_of_chunks_in_batch = len(batch)

        if number_of_embeddings != number_of_chunks_in_batch:
            raise RuntimeError(
                "The number of embeddings does not match "
                "the number of chunks."
            )

        store_batch(
            collection=collection,
            batch=batch,
            embeddings=embeddings,
        )

        processed_chunks += number_of_chunks_in_batch

        print(
            f"Batch {batch_number}: "
            f"stored {processed_chunks}/{total_chunks} chunks"
        )

    collection_size = collection.count()

    print(f"Collection records: {collection_size}")
    print(f"Chroma database: {CHROMA_PATH}")
    print(f"Collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()