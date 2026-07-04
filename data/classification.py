import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

BATCH_SIZE = 10
MAX_CLASSIFICATION_RETRIES = 5

ALLOWED_CATEGORIES = {
    "Authentication Issues",
    "Account Suspension",
    "Performance Issues",
    "Messaging & DMs",
    "Reels & Feed Algorithm",
    "Privacy Concerns",
    "Content Moderation",
    "Feature Requests",
    "Customer Support",
    "Creator Tools",
    "General Feedback",
}

ALLOWED_SENTIMENTS = {
    "positive",
    "neutral",
    "negative",
}


def extract_json(content: str):
    content = content.strip()

    if content.startswith("```json"):
        content = content.replace("```json", "")
        content = content.replace("```", "")
    elif content.startswith("```"):
        content = content.replace("```", "")

    return json.loads(content.strip())


def parse_quality_score(value):
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 1

    return max(1, min(5, score))


def get_retry_delay_seconds(error, attempt):
    response = getattr(error, "response", None)

    if response is not None:
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return max(1, int(float(retry_after)))
            except ValueError:
                pass

        if response.status_code == 429:
            return min(120, 30 * attempt)

    return attempt * 2


def classify_reviews_batch(review_texts):
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. "
            "Add it to .env before running classification."
        )

    review_payload = [
        {
            "id": idx,
            "text": text,
        }
        for idx, text in enumerate(review_texts)
    ]

    prompt = f"""
You are a customer feedback analyst.

Choose exactly ONE category using these meanings:
    - Authentication Issues: Login, signup, password reset, two-factor authentication, verification codes, session expiry, hacked-account recovery, or being unable to access an account because authentication is failing.
    - Account Suspension: Disabled, banned, suspended, restricted, locked, removed, or deactivated accounts; appeals; account status warnings; suspected policy violations causing loss of account access.
    - Performance Issues: App crashes, freezes, slow loading, lag, battery drain, overheating, upload/download failures, blank screens, update bugs, broken notifications, or other technical reliability problems.
    - Messaging & DMs: Direct messages, message requests, group chats, disappearing messages, media sharing in chat, inbox behavior, message delivery, calling from chat, or unwanted contact through DMs.
    - Reels & Feed Algorithm: Reels, feed ranking, recommendations, suggested posts, Explore content, algorithm quality, repetitive content, irrelevant posts, reach/discovery in the feed, or short-video viewing experience.
    - Privacy Concerns: Private account controls, data use, tracking, visibility of posts/stories/activity, location sharing, contacts sync, blocked/restricted users, message privacy, or who can see/contact the user.
    - Content Moderation: Removal, flagging, reporting, appeals, community guidelines, hate/harassment/spam/graphic content enforcement, or complaints that unsafe content is allowed or normal content is taken down.
    - Feature Requests: Requests for new features, restoring old features, UI changes, customization, missing options, or product improvements that are not primarily bug reports.
    - Customer Support: Help center, support tickets, response delays, inability to contact support, poor support experience, unresolved reports, or frustration with getting human/helpful assistance.
    - Creator Tools: Professional dashboard, insights/analytics, creator/business accounts, monetization, branded content, post/reel editing tools, scheduling, audience growth tools, or creator workflow problems.
    - General Feedback: Broad opinions, unclear complaints, vague rants, generic praise, mixed comments without a dominant category, or feedback that does not fit the other categories.

    Classification rules:
    - Pick the most specific category that matches the main issue in the feedback.
    - For positive feedback, choose the specific product area being praised.
    - If positive feedback is generic praise without a clear product area, choose General Feedback.
    - If feedback mentions multiple issues, choose the one the user emphasizes most.
    - Use General Feedback only when no specific category clearly applies.

Allowed sentiments:
- positive
- neutral
- negative

Quality Score Guidelines:

1 = Nonsense, emojis only, names only, random words,
    impossible to understand.

2 = Very short opinion with little information.
    Example:
    "good app"
    "bad update"

3 = Understandable feedback with some useful information.

4 = Clear feedback describing a specific issue,
    request, complaint, or positive experience.

5 = Detailed and actionable feedback containing:
    - context
    - specific issue/request
    - explanation of impact

Feedback:
{json.dumps(review_payload)}

Return ONLY a JSON array with exactly one object for each feedback item.
Each output object MUST keep the same id as the input item.
Do not add extra objects.
Do not skip any input item.

Example:
[
  {{
    "id": 0,
    "category": "Performance Issues",
    "sentiment": "negative",
    "quality_score": 5
  }}
]
"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/gpt-oss-120b:free",
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        },
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    return extract_json(content)


def normalize_classification_results(results, batch_size):
    if not isinstance(results, list):
        raise ValueError(
            "Batch classification response was not a JSON array."
        )

    results_by_id = {}
    missing_ids = []

    for position, result in enumerate(results):
        if not isinstance(result, dict):
            continue

        result_id = result.get("id")

        if result_id is None:
            result_id = position

        try:
            result_id = int(result_id)
        except (TypeError, ValueError):
            continue

        if 0 <= result_id < batch_size and result_id not in results_by_id:
            results_by_id[result_id] = result

    normalized = []

    for result_id in range(batch_size):
        result = results_by_id.get(result_id)

        if result is None:
            missing_ids.append(result_id)
            continue

        category = result.get("category")
        sentiment = result.get("sentiment")

        if category not in ALLOWED_CATEGORIES:
            missing_ids.append(result_id)
            continue

        if sentiment not in ALLOWED_SENTIMENTS:
            missing_ids.append(result_id)
            continue

        normalized.append(
            {
                "category": category,
                "sentiment": sentiment,
                "quality_score": parse_quality_score(
                    result.get("quality_score")
                ),
            }
        )

    if missing_ids:
        raise ValueError(
            "Missing or invalid classifications for review ids: "
            f"{missing_ids}"
        )

    return normalized


def classify_reviews_batch_with_retry(batch):
    last_error = None

    for attempt in range(1, MAX_CLASSIFICATION_RETRIES + 1):
        try:
            results = classify_reviews_batch(batch)
            return normalize_classification_results(
                results,
                len(batch)
            )

        except Exception as e:
            last_error = e

            print(
                "Classification retry "
                f"{attempt}/{MAX_CLASSIFICATION_RETRIES} failed: {e}"
            )

            if attempt < MAX_CLASSIFICATION_RETRIES:
                time.sleep(
                    get_retry_delay_seconds(
                        e,
                        attempt,
                    )
                )

    raise RuntimeError(
        "Classification failed after "
        f"{MAX_CLASSIFICATION_RETRIES} retries."
    ) from last_error


def build_classification_text(row):
    review_text = row.get("review_text")

    if isinstance(review_text, str) and review_text.strip():
        return review_text.strip()

    title = row.get("title")
    body = row.get("body")
    parts = [
        value.strip()
        for value in [title, body]
        if isinstance(value, str) and value.strip()
    ]

    return "\n\n".join(parts)


def classify_dataframe(
    df,
    text_column="review_text",
    batch_size=BATCH_SIZE,
    sleep_seconds=1,
    verbose=True,
):
    if df.empty:
        df = df.copy()
        df["category"] = []
        df["sentiment"] = []
        df["quality_score"] = []
        return df

    df = df.copy()

    if text_column in df.columns:
        texts = df[text_column].fillna("").astype(str).tolist()
    else:
        texts = [
            build_classification_text(row)
            for _, row in df.iterrows()
        ]

    categories = []
    sentiments = []
    quality_scores = []

    total_batches = (
        len(texts) + batch_size - 1
    ) // batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        if verbose:
            print(
                f"Classifying batch "
                f"{i // batch_size + 1}/{total_batches}"
            )

        results = classify_reviews_batch_with_retry(batch)

        for result in results:
            categories.append(
                result.get("category", "General Feedback")
            )
            sentiments.append(
                result.get("sentiment", "neutral")
            )
            quality_scores.append(
                parse_quality_score(
                    result.get("quality_score", 1)
                )
            )

        if sleep_seconds:
            time.sleep(sleep_seconds)

    df["category"] = categories
    df["sentiment"] = sentiments
    df["quality_score"] = quality_scores

    return df
