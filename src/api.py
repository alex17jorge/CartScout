import os
from pathlib import Path
from typing import Literal

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "cartscout-patches-v1"
EMBEDDING_MODEL = "text-embedding-3-small"
NUMBER_OF_RESULTS = 6

load_dotenv(PROJECT_ROOT / ".env")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-sol")

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = chroma_client.get_collection(COLLECTION_NAME)

app = FastAPI(title="Patch Notes Buddy API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


class Source(BaseModel):
    patch: str | None = None
    section: str | None = None
    entity: str | None = None
    source: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


def embed_query(query: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
        encoding_format="float",
    )
    return response.data[0].embedding


def retrieve_chunks(query: str) -> list[dict]:
    query_embedding = embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=NUMBER_OF_RESULTS,
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        chunks.append(
            {
                "document": document,
                "metadata": metadata or {},
                "distance": distance,
            }
        )

    return chunks


def build_context(chunks: list[dict]) -> str:
    context_blocks = []

    for index, chunk in enumerate(chunks, start=1):
        context_blocks.append(f"[Source {index}]\n{chunk['document']}")

    return "\n\n".join(context_blocks)


def build_search_query(request: ChatRequest) -> str:
    recent_user_messages = [
        message.content
        for message in request.history
        if message.role == "user"
    ][-2:]
    return "\n".join([*recent_user_messages, request.message])


def build_conversation(request: ChatRequest, context: str) -> list[dict]:
    conversation = []

    for message in request.history[-8:]:
        conversation.append(
            {"role": message.role, "content": message.content}
        )

    conversation.append(
        {
            "role": "user",
            "content": (
                f"Question:\n{request.message}\n\n"
                f"Retrieved patch-note context:\n{context}"
            ),
        }
    )
    return conversation


def make_sources(chunks: list[dict]) -> list[Source]:
    sources = []
    seen = set()

    for chunk in chunks:
        metadata = chunk["metadata"]
        source_key = (
            metadata.get("patch"),
            metadata.get("section"),
            metadata.get("entity"),
        )

        if source_key in seen:
            continue

        seen.add(source_key)
        sources.append(
            Source(
                patch=metadata.get("patch"),
                section=metadata.get("section"),
                entity=metadata.get("entity"),
                source=metadata.get("source"),
            )
        )

    return sources


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "chunks": collection.count(),
        "embedding_model": EMBEDDING_MODEL,
        "chat_model": CHAT_MODEL,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        chunks = retrieve_chunks(build_search_query(request))

        if not chunks:
            raise HTTPException(
                status_code=404,
                detail="No relevant patch-note chunks were found.",
            )

        context = build_context(chunks)
        response = openai_client.responses.create(
            model=CHAT_MODEL,
            reasoning={"effort": "low"},
            instructions=(
                "You are Patch Notes Buddy, an assistant for League of Legends "
                "patch notes. Answer only from the retrieved context. Be clear "
                "and concise. Mention patch numbers when relevant. If the context "
                "does not support the answer, say that you do not have enough "
                "information. Do not invent changes."
            ),
            input=build_conversation(request, context),
            store=False,
        )

        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("The model returned an empty response.")

        return ChatResponse(
            answer=answer,
            sources=make_sources(chunks),
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="The patch-note assistant could not answer right now.",
        ) from error
