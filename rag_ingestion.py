import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DEFAULT_INPUT_FILE = "data/instagram_reviews_rag.csv"
DEFAULT_CHECKPOINT_FILE = "data/rag_ingestion_checkpoint.json"
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "instagram_feedback")
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_BATCH_SIZE = 64


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def load_checkpoint(path):
    path = Path(path)

    if not path.exists():
        return {
            "processed_ids": [],
            "failed": {},
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }

    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path, checkpoint):
    checkpoint["updated_at"] = utc_now_iso()
    checkpoint["processed_ids"] = sorted(
        set(checkpoint.get("processed_ids", []))
    )
    atomic_write_json(path, checkpoint)


def stable_point_id(review_id):
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"customer-feedback:{review_id}",
        )
    )


def normalize_value(value):
    if pd.isna(value):
        return None

    return value


def build_document_text(row):
    parts = [
        f"Review: {row.get('review_text', '')}",
        f"Category: {row.get('category', '')}",
        f"Sentiment: {row.get('sentiment', '')}",
        f"Source: {row.get('source', '')}",
    ]

    return "\n".join(
        part
        for part in parts
        if part.split(":", 1)[1].strip()
    )


def build_payload(row):
    return {
        "review_id": str(row["review_id"]),
        "source": normalize_value(row.get("source")),
        "user_rating": normalize_value(row.get("user_rating")),
        "review_text": normalize_value(row.get("review_text")),
        "category": normalize_value(row.get("category")),
        "review_date": normalize_value(row.get("review_date")),
        "sentiment": normalize_value(row.get("sentiment")),
        "quality_score": normalize_value(row.get("quality_score")),
    }


def load_records(input_file):
    df = pd.read_csv(input_file)

    required_columns = {
        "review_id",
        "source",
        "review_text",
        "category",
        "review_date",
        "sentiment",
        "quality_score",
    }
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Input CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    df = df.dropna(subset=["review_id", "review_text"]).copy()
    df["review_id"] = df["review_id"].astype(str)
    df["document_text"] = [
        build_document_text(row)
        for _, row in df.iterrows()
    ]

    return df.to_dict(orient="records")


def batches(items, batch_size):
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def filter_unprocessed(records, checkpoint):
    processed_ids = set(checkpoint.get("processed_ids", []))

    return [
        record
        for record in records
        if str(record["review_id"]) not in processed_ids
    ]


def get_openai_client():
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required to create embeddings."
        )

    return OpenAI(
        api_key=api_key,
    )


def get_qdrant_client():
    from qdrant_client import QdrantClient

    qdrant_url = (
        os.getenv("QDRANT_URL")
        or os.getenv("QDRANT_CLUSTER_ENDPOINT")
        or "http://localhost:6333"
    )
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    return QdrantClient(
        url=qdrant_url,
        api_key=qdrant_api_key,
    )


def ensure_collection(client, collection_name, vector_size):
    from qdrant_client import models

    try:
        exists = client.collection_exists(collection_name)
    except AttributeError:
        try:
            client.get_collection(collection_name)
            exists = True
        except Exception:
            exists = False

    if exists:
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )


def embed_texts_with_dimensions(client, texts, model, dimensions):
    kwargs = {
        "model": model,
        "input": texts,
    }

    if dimensions:
        kwargs["dimensions"] = dimensions

    response = client.embeddings.create(**kwargs)

    return [
        item.embedding
        for item in response.data
    ]


def upsert_records(client, collection_name, records, vectors):
    from qdrant_client import models

    points = [
        models.PointStruct(
            id=stable_point_id(record["review_id"]),
            vector=vector,
            payload=build_payload(record),
        )
        for record, vector in zip(records, vectors)
    ]

    client.upsert(
        collection_name=collection_name,
        points=points,
        wait=True,
    )


def fingerprint_input(input_file):
    digest = hashlib.sha256()
    path = Path(input_file)

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def ingest(
    input_file=DEFAULT_INPUT_FILE,
    checkpoint_file=DEFAULT_CHECKPOINT_FILE,
    collection_name=DEFAULT_COLLECTION,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
    batch_size=DEFAULT_BATCH_SIZE,
    limit=None,
    reset_checkpoint=False,
):
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    if reset_checkpoint and Path(checkpoint_file).exists():
        Path(checkpoint_file).unlink()

    records = load_records(input_file)

    if limit:
        records = records[:limit]

    checkpoint = load_checkpoint(checkpoint_file)
    metadata = {
        "input_file": str(input_file),
        "input_sha256": fingerprint_input(input_file),
        "collection_name": collection_name,
        "embedding_model": embedding_model,
        "embedding_dimensions": embedding_dimensions,
    }

    for key, value in metadata.items():
        checkpoint.setdefault(key, value)

        if checkpoint[key] != value:
            raise RuntimeError(
                f"Checkpoint {checkpoint_file} was created with a different "
                f"{key}. Use --reset-checkpoint or pass a different "
                "checkpoint path."
            )

    checkpoint.setdefault("failed", {})
    checkpoint.setdefault("processed_ids", [])
    checkpoint["total_records"] = len(records)
    save_checkpoint(checkpoint_file, checkpoint)

    remaining_records = filter_unprocessed(records, checkpoint)

    if not remaining_records:
        print("No new records to ingest.")
        return checkpoint

    openai_client = get_openai_client()
    qdrant_client = get_qdrant_client()

    ensure_collection(
        qdrant_client,
        collection_name,
        embedding_dimensions,
    )

    total_batches = (
        len(remaining_records) + batch_size - 1
    ) // batch_size

    for batch_index, batch_records in enumerate(
        batches(remaining_records, batch_size),
        start=1,
    ):
        batch_ids = [
            str(record["review_id"])
            for record in batch_records
        ]

        print(
            f"Ingesting batch {batch_index}/{total_batches} "
            f"({len(batch_records)} records)"
        )

        try:
            vectors = embed_texts_with_dimensions(
                openai_client,
                [
                    record["document_text"]
                    for record in batch_records
                ],
                embedding_model,
                embedding_dimensions,
            )
            upsert_records(
                qdrant_client,
                collection_name,
                batch_records,
                vectors,
            )
        except Exception as e:
            error_message = str(e)

            for review_id in batch_ids:
                checkpoint["failed"][review_id] = {
                    "error": error_message,
                    "failed_at": utc_now_iso(),
                }

            save_checkpoint(checkpoint_file, checkpoint)
            print(
                "Batch failed. Progress checkpoint saved to "
                f"{checkpoint_file}"
            )
            raise

        checkpoint["processed_ids"].extend(batch_ids)

        for review_id in batch_ids:
            checkpoint["failed"].pop(review_id, None)

        save_checkpoint(checkpoint_file, checkpoint)
        time.sleep(0.2)

    print(
        "Ingestion complete. "
        f"Processed {len(checkpoint['processed_ids'])} total records."
    )

    return checkpoint


def parse_args():
    parser = argparse.ArgumentParser(
        description="Embed feedback rows and upsert them into Qdrant."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT_FILE)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument(
        "--dimensions",
        type=int,
        default=DEFAULT_EMBEDDING_DIMENSIONS,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("RAG_INGEST_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    ingest(
        input_file=args.input,
        checkpoint_file=args.checkpoint,
        collection_name=args.collection,
        embedding_model=args.model,
        embedding_dimensions=args.dimensions,
        batch_size=args.batch_size,
        limit=args.limit,
        reset_checkpoint=args.reset_checkpoint,
    )


if __name__ == "__main__":
    main()
