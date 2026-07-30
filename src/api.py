import os
import re
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
PATCH_PATTERN = re.compile(r"\b(?:patch\s*)?(\d{1,2}\.\d{1,2})\b", re.IGNORECASE)
SECTION_TERMS = {
    "items": ("item", "items"),
    "champions": ("champion", "champions"),
    "runes": ("rune", "runes"),
    "summoner_spells": ("summoner spell", "summoner spells"),
    "monsters": ("monster", "monsters", "jungle monster", "jungle monsters"),
    "arena": ("arena",),
    "aram_mayhem": ("aram mayhem", "aram: mayhem"),
    "client": ("client",),
    "game": ("game system", "game systems"),
}

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
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)


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


def make_where_filter(patch: str | None, section: str | None) -> dict | None:
    filters = []

    if patch:
        filters.append({"patch": patch})

    if section:
        filters.append({"section": section})

    if len(filters) == 1:
        return filters[0]

    if len(filters) > 1:
        return {"$and": filters}

    return None


def retrieve_chunks(
    query: str,
    patch: str | None = None,
    section: str | None = None,
) -> list[dict]:
    query_embedding = embed_query(query)
    query_arguments = {
        "query_embeddings": [query_embedding],
        "n_results": NUMBER_OF_RESULTS,
        "include": ["documents", "metadatas", "distances"],
    }
    where_filter = make_where_filter(patch, section)

    if where_filter:
        query_arguments["where"] = where_filter

    results = collection.query(
        **query_arguments,
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


def retrieve_complete_section(patch: str, section: str) -> list[dict]:
    results = collection.get(
        where=make_where_filter(patch, section),
        include=["documents", "metadatas"],
    )

    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])

    return [
        {
            "document": document,
            "metadata": metadata or {},
            "distance": None,
        }
        for document, metadata in zip(documents, metadatas)
    ]


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


def get_latest_patch() -> str | None:
    results = collection.get(include=["metadatas"])
    patches = {
        metadata.get("patch")
        for metadata in results.get("metadatas", [])
        if metadata and metadata.get("patch")
    }

    valid_patches = []
    for patch in patches:
        try:
            patch_key = tuple(int(part) for part in patch.split("."))
        except (AttributeError, ValueError):
            continue

        valid_patches.append((patch_key, patch))

    if not valid_patches:
        return None

    return max(valid_patches)[1]


def find_patch(text: str) -> str | None:
    match = PATCH_PATTERN.search(text)
    return match.group(1) if match else None


def mentions_latest_patch(text: str) -> bool:
    lowered_text = text.lower()
    return "latest patch" in lowered_text or "new patch" in lowered_text


def resolve_patch(request: ChatRequest) -> str | None:
    explicit_patch = find_patch(request.message)
    if explicit_patch:
        return explicit_patch

    if mentions_latest_patch(request.message):
        return get_latest_patch()

    for message in reversed(request.history):
        if message.role != "user":
            continue

        explicit_patch = find_patch(message.content)
        if explicit_patch:
            return explicit_patch

        if mentions_latest_patch(message.content):
            return get_latest_patch()

    return get_latest_patch()


def find_section(text: str) -> str | None:
    lowered_text = text.lower()

    for section, terms in SECTION_TERMS.items():
        if any(term in lowered_text for term in terms):
            return section

    return None


def resolve_section(request: ChatRequest) -> str | None:
    section = find_section(request.message)
    if section:
        return section

    for message in reversed(request.history):
        if message.role != "user":
            continue

        section = find_section(message.content)
        if section:
            return section

    return None


def mentions_entity(question: str, chunks: list[dict]) -> bool:
    lowered_question = question.lower()

    for chunk in chunks:
        entity = chunk["metadata"].get("entity")
        if entity and entity.lower() in lowered_question:
            return True

    return False


def is_complete_section_question(
    question: str,
    section: str,
    section_chunks: list[dict],
) -> bool:
    if mentions_entity(question, section_chunks):
        return False

    lowered_question = question.lower()
    mentions_section = any(
        term in lowered_question
        for term in SECTION_TERMS.get(section, ())
    )
    asks_for_list = any(
        marker in lowered_question
        for marker in ("all", "every", "list", "which")
    )
    asks_what_changed = (
        "what" in lowered_question
        and any(
            marker in lowered_question
            for marker in ("change", "changed", "changes", "happened")
        )
    )

    return asks_for_list or (mentions_section and asks_what_changed)


def retrieve_for_request(request: ChatRequest) -> tuple[list[dict], bool]:
    patch = resolve_patch(request)
    section = resolve_section(request)

    if patch and section:
        section_chunks = retrieve_complete_section(patch, section)

        if section_chunks and is_complete_section_question(
            request.message,
            section,
            section_chunks,
        ):
            return section_chunks, True

    chunks = retrieve_chunks(
        query=build_search_query(request),
        patch=patch,
        section=section,
    )
    return chunks, False


def build_conversation(request: ChatRequest, context: str) -> list[dict]:
    conversation = []

    for message in request.history[-50:]:
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
        chunks, complete_section = retrieve_for_request(request)

        if not chunks:
            raise HTTPException(
                status_code=404,
                detail="No relevant patch-note chunks were found.",
            )

        context = build_context(chunks)
        coverage_instruction = (
            "The retrieved context contains every stored record matching the "
            "requested patch and section. Include every distinct entity in "
            "your answer; do not reduce the answer to only one example."
            if complete_section
            else "Answer the specific question using the most relevant retrieved records."
        )
        response = openai_client.responses.create(
            model=CHAT_MODEL,
            reasoning={"effort": "low"},
            instructions=(
                f"""
                    You are Patch Notes Buddy, a friendly and helpful League of Legends patch-notes assistant.

                    Answer using only the retrieved context. Speak naturally, like a knowledgeable friend explaining the changes in chat.

                    Keep answers clear, concise, and easy to understand. Mention the relevant patch number whenever it is available. When useful, explain whether a change is a buff, nerf, adjustment, or bug fix, but only when the context supports that conclusion.

                    Do not invent changes, numbers, champions, items, abilities, or patch details. If the retrieved context does not contain enough information to answer confidently, say something friendly such as:

                    "I couldn't find enough information about that in the patch notes I have."

                    Do not pretend to know information outside the retrieved context.

                    {coverage_instruction}
                """
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
