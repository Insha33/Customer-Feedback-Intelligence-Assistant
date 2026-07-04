import json
import math
import os
import re
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from prompts import SYSTEM_PROMPT, build_user_prompt

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()
else:
    env_path = Path(__file__).resolve().parent / ".env"

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

HOST = os.getenv("REVIEWLENS_HOST", "127.0.0.1")
PORT = int(os.getenv("REVIEWLENS_PORT", "8080"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "instagram_feedback")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "openai/gpt-4.1-mini")
RETRIEVAL_LIMIT = int(os.getenv("RAG_RETRIEVAL_LIMIT", "12"))
DENSE_LIMIT = int(os.getenv("RAG_DENSE_LIMIT", "28"))
LEXICAL_LIMIT = int(os.getenv("RAG_LEXICAL_LIMIT", "28"))
DOC_CACHE_SECONDS = int(os.getenv("RAG_DOC_CACHE_SECONDS", "300"))

WORD_RE = re.compile(r"[a-z0-9']+")
DOC_CACHE = {
    "loaded_at": 0,
    "docs": [],
}


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))

    if length <= 0:
        return {}

    return json.loads(handler.rfile.read(length).decode("utf-8"))


def get_openai_client():
    from openai import OpenAI

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required.")

    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_openrouter_client():
    from openai import OpenAI

    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is required for Ask AI answers.")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": os.getenv(
                "OPENROUTER_SITE_URL",
                f"http://{HOST}:{PORT}",
            ),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "ReviewLens"),
        },
    )


def get_qdrant_client():
    from qdrant_client import QdrantClient

    qdrant_url = (
        os.getenv("QDRANT_URL")
        or os.getenv("QDRANT_CLUSTER_ENDPOINT")
        or "http://localhost:6333"
    )

    return QdrantClient(
        url=qdrant_url,
        api_key=os.getenv("QDRANT_API_KEY"),
    )


def tokenize(text):
    return WORD_RE.findall((text or "").lower())


def payload_text(payload):
    return "\n".join(
        str(payload.get(key) or "")
        for key in [
            "review_text",
            "category",
            "sentiment",
            "source",
            "review_date",
            "user_rating",
        ]
    )


def point_to_doc(point):
    payload = point.payload or {}
    review_id = str(payload.get("review_id") or point.id)

    return {
        "id": review_id,
        "point_id": str(point.id),
        "payload": payload,
        "text": payload_text(payload),
    }


def load_qdrant_documents(client):
    now = time.time()

    if DOC_CACHE["docs"] and now - DOC_CACHE["loaded_at"] < DOC_CACHE_SECONDS:
        return DOC_CACHE["docs"]

    docs = []
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        docs.extend(point_to_doc(point) for point in points)

        if offset is None:
            break

    DOC_CACHE["docs"] = docs
    DOC_CACHE["loaded_at"] = now
    return docs


def embed_query(openai_client, question):
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question,
    )

    return response.data[0].embedding


def dense_search(qdrant_client, query_vector):
    try:
        result = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=DENSE_LIMIT,
            with_payload=True,
        )
        points = result.points
    except AttributeError:
        points = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=DENSE_LIMIT,
            with_payload=True,
        )

    return [point_to_doc(point) for point in points]


def lexical_search(question, docs):
    query_terms = tokenize(question)

    if not query_terms or not docs:
        return []

    doc_terms = [tokenize(doc["text"]) for doc in docs]
    doc_count = len(doc_terms)
    avg_doc_len = sum(len(terms) for terms in doc_terms) / max(doc_count, 1)
    document_frequency = {}

    for terms in doc_terms:
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    scores = []
    k1 = 1.2
    b = 0.75

    for doc, terms in zip(docs, doc_terms):
        if not terms:
            continue

        term_counts = {}
        for term in terms:
            term_counts[term] = term_counts.get(term, 0) + 1

        score = 0.0
        for term in query_terms:
            if term not in term_counts:
                continue

            idf = math.log(
                1 + (doc_count - document_frequency.get(term, 0) + 0.5)
                / (document_frequency.get(term, 0) + 0.5)
            )
            frequency = term_counts[term]
            denominator = frequency + k1 * (1 - b + b * len(terms) / avg_doc_len)
            score += idf * (frequency * (k1 + 1)) / denominator

        if score > 0:
            scores.append((score, doc))

    return [
        doc
        for _, doc in sorted(scores, key=lambda item: item[0], reverse=True)[
            :LEXICAL_LIMIT
        ]
    ]


def reciprocal_rank_fusion(result_lists, limit):
    scores = {}
    docs_by_id = {}
    k = 60

    for results in result_lists:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc["id"]
            docs_by_id[doc_id] = doc
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (k + rank)

    ranked_ids = sorted(scores, key=scores.get, reverse=True)
    return [docs_by_id[doc_id] for doc_id in ranked_ids[:limit]]


def source_summary(doc):
    payload = doc["payload"]
    return {
        "review_id": str(payload.get("review_id") or doc["id"]),
        "category": payload.get("category"),
        "sentiment": payload.get("sentiment"),
        "source": payload.get("source"),
        "review_date": payload.get("review_date"),
        "review_text": payload.get("review_text"),
    }


def build_context(docs):
    chunks = []

    for index, doc in enumerate(docs, start=1):
        payload = doc["payload"]
        chunks.append(
            "\n".join(
                [
                    f"[{index}] review_id: {payload.get('review_id') or doc['id']}",
                    f"category: {payload.get('category')}",
                    f"sentiment: {payload.get('sentiment')}",
                    f"rating: {payload.get('user_rating')}",
                    f"date: {payload.get('review_date')}",
                    f"source: {payload.get('source')}",
                    f"text: {payload.get('review_text')}",
                ]
            )
        )

    return "\n\n".join(chunks)


def answer_question(openrouter_client, question, docs):
    context = build_context(docs)
    user_prompt = build_user_prompt(question, context)

    response = openrouter_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content


def handle_chat(question):
    question = (question or "").strip()

    if not question:
        raise ValueError("Question is required.")

    openai_client = get_openai_client()
    openrouter_client = get_openrouter_client()
    qdrant_client = get_qdrant_client()
    query_vector = embed_query(openai_client, question)
    docs = load_qdrant_documents(qdrant_client)
    dense_results = dense_search(qdrant_client, query_vector)
    lexical_results = lexical_search(question, docs)
    fused_docs = reciprocal_rank_fusion(
        [dense_results, lexical_results],
        RETRIEVAL_LIMIT,
    )

    if not fused_docs:
        return {
            "answer": "I could not find matching reviews in the Qdrant collection.",
            "sources": [],
        }

    return {
        "answer": answer_question(openrouter_client, question, fused_docs),
        "sources": [source_summary(doc) for doc in fused_docs],
        "retrieval": {
            "mode": "dense_vector_plus_lexical_rrf",
            "dense_candidates": len(dense_results),
            "lexical_candidates": len(lexical_results),
            "returned_contexts": len(fused_docs),
        },
    }


class ReviewLensHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.endswith((".html", ".js", ".css")) or self.path.startswith(
            "/api/"
        ):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            return json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "collection": COLLECTION_NAME,
                    "embedding_model": EMBEDDING_MODEL,
                    "chat_model": CHAT_MODEL,
                    "chat_provider": "openrouter",
                    "qdrant_configured": bool(
                        os.getenv("QDRANT_URL")
                        or os.getenv("QDRANT_CLUSTER_ENDPOINT")
                    ),
                    "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
                    "openrouter_configured": bool(
                        os.getenv("OPENROUTER_API_KEY")
                    ),
                },
            )

        if parsed.path == "/":
            self.path = "/frontend/"
        elif parsed.path == "/chat":
            self.path = "/frontend/chat.html"

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path != "/api/chat":
            return json_response(
                self,
                HTTPStatus.NOT_FOUND,
                {"error": "Unknown API route."},
            )

        try:
            payload = read_json_body(self)
            result = handle_chat(payload.get("question"))
            return json_response(self, HTTPStatus.OK, result)
        except Exception as error:
            return json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(error)},
            )


def main():
    os.chdir(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer((HOST, PORT), ReviewLensHandler)
    print(f"ReviewLens running at http://{HOST}:{PORT}/frontend/")
    print(f"Ask AI page running at http://{HOST}:{PORT}/frontend/chat.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
