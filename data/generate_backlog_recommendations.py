import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit("The openai package is required to generate backlog actions.") from exc


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "instagram_reviews_rag.csv"
OUTPUT_JSON = ROOT / "data" / "backlog_recommendations.json"
LANES = ["Must implement", "Should have", "Nice to have"]


def model_name():
    return os.getenv("OPENROUTER_BACKLOG_MODEL") or os.getenv(
        "OPENROUTER_CHAT_MODEL",
        "openai/gpt-4.1-mini",
    )


def load_environment():
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        return

    env_path = ROOT / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_reviews(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def pct(value, total):
    if not total:
        return 0
    return round((value / total) * 100)


def summarize_reviews(rows):
    category_rows = defaultdict(list)
    for row in rows:
        category_rows[row.get("category") or "Unknown"].append(row)

    category_summaries = []
    for category, items in sorted(
        category_rows.items(),
        key=lambda entry: len(entry[1]),
        reverse=True,
    ):
        sentiment = Counter((row.get("sentiment") or "unknown").lower() for row in items)
        low_rating = sum(1 for row in items if int(row.get("user_rating") or 0) <= 2)
        avg_rating = sum(float(row.get("user_rating") or 0) for row in items) / max(
            len(items),
            1,
        )
        examples = sorted(
            items,
            key=lambda row: (
                (row.get("sentiment") or "").lower() == "negative",
                int(row.get("quality_score") or 0),
                int(row.get("user_rating") or 0) <= 2,
            ),
            reverse=True,
        )[:4]
        category_summaries.append(
            {
                "category": category,
                "review_count": len(items),
                "negative_pct": pct(sentiment.get("negative", 0), len(items)),
                "low_rating_pct": pct(low_rating, len(items)),
                "average_rating": round(avg_rating, 2),
                "examples": [
                    {
                        "review_id": row.get("review_id"),
                        "rating": row.get("user_rating"),
                        "sentiment": row.get("sentiment"),
                        "text": (row.get("review_text") or "")[:450],
                    }
                    for row in examples
                ],
            }
        )

    return {
        "total_reviews": len(rows),
        "category_summaries": category_summaries[:12],
        "source_counts": Counter(row.get("source") or "unknown" for row in rows),
        "sentiment_counts": Counter((row.get("sentiment") or "unknown").lower() for row in rows),
    }


def build_prompt(summary):
    return f"""
You are a senior product manager generating a backlog from Instagram review analysis.

Create 8 to 12 action recommendations from the data below. Do not copy category names as the action.
Each action should be specific, implementation-oriented, and based on evidence in the reviews.
Write impact as a concrete product outcome, not generic phrases like "reduce churn".
Prefer measurable PM language such as fewer wrongful lockouts, fewer support escalations,
higher account recovery completion, lower crash frequency, or improved feed relevance.

Return ONLY valid JSON with this exact structure:
{{
  "recommendations": [
    {{
      "lane": "Must implement | Should have | Nice to have",
      "action": "Specific recommended product/support/engineering action",
      "categories": ["Category 1", "Category 2"],
      "evidence": "Short evidence summary grounded in review patterns",
      "impact": "User/business impact",
      "confidence": "high | medium | low"
    }}
  ]
}}

Prioritization rules:
- Must implement: severe account access, account loss, crashes, broken core flows, repeated one-star pain.
- Should have: important usability, support, trust, ranking, messaging, or creator workflow problems.
- Nice to have: smaller improvements, quality-of-life requests, polish, non-blocking enhancements.

Dataset summary:
{json.dumps(summary, ensure_ascii=False)}
""".strip()


def openrouter_client():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required.")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://127.0.0.1:8080"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "ReviewLens"),
        },
    )


def generate_recommendations(summary):
    response = openrouter_client().chat.completions.create(
        model=model_name(),
        messages=[
            {
                "role": "system",
                "content": "Return concise product backlog JSON only. No markdown.",
            },
            {"role": "user", "content": build_prompt(summary)},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.removeprefix("json").strip()
    data = json.loads(content)
    recommendations = data.get("recommendations", [])

    for recommendation in recommendations:
        if recommendation.get("lane") not in LANES:
            raise ValueError(f"Invalid lane: {recommendation.get('lane')}")

    return recommendations


def write_output(recommendations, rows, csv_hash):
    payload = {
        "metadata": {
            "source_csv": str(INPUT_CSV.relative_to(ROOT)),
            "source_csv_sha256": csv_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "data/generate_backlog_recommendations.py",
            "model": model_name(),
            "total_reviews": len(rows),
        },
        "recommendations": recommendations,
    }
    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def existing_output_matches(csv_hash):
    if not OUTPUT_JSON.exists():
        return False

    try:
        payload = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    return payload.get("metadata", {}).get("source_csv_sha256") == csv_hash


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate LLM backlog recommendations from Instagram reviews.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when the CSV hash has not changed.",
    )
    parser.add_argument(
        "--allow-stale-on-error",
        action="store_true",
        help="Keep an existing output file if regeneration fails.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    load_environment()
    rows = read_reviews(INPUT_CSV)
    csv_hash = file_sha256(INPUT_CSV)

    if not args.force and existing_output_matches(csv_hash):
        print(f"{OUTPUT_JSON} is already current for CSV SHA256: {csv_hash}")
        return

    summary = summarize_reviews(rows)
    try:
        recommendations = generate_recommendations(summary)
    except Exception:
        if args.allow_stale_on_error and OUTPUT_JSON.exists():
            print(
                "Backlog regeneration failed; keeping existing "
                f"{OUTPUT_JSON}.",
            )
            return
        raise

    write_output(recommendations, rows, csv_hash)
    print(f"Wrote {len(recommendations)} recommendations to {OUTPUT_JSON}")
    print(f"CSV SHA256: {csv_hash}")


if __name__ == "__main__":
    main()
