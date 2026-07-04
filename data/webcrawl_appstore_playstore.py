import json
import time
import requests
import pandas as pd
import langid

from datetime import datetime, timedelta
from google_play_scraper import reviews, Sort
from classification import classify_dataframe

APP_ID = "com.instagram.android"
APPSTORE_APP_ID = "389801252"
APPSTORE_COUNTRY = "us"

TARGET_PLAYSTORE = 300
TARGET_APPSTORE = 300
SCRAPE_LIMIT = 1000
APPSTORE_PAGE_SIZE = 50
APPSTORE_MAX_PAGES = 10

def is_english(text):
    if not text or len(text.strip()) < 5:
        return False

    try:
        lang, _ = langid.classify(text)
        return lang == "en"
    except Exception:
        return False
    
def scrape_playstore_reviews():
    all_reviews = []
    token = None

    one_year_ago = datetime.now() - timedelta(days=365)

    while len(all_reviews) < SCRAPE_LIMIT:

        result, token = reviews(
            APP_ID,
            lang="en",
            country="us",
            sort=Sort.NEWEST,
            count=200,
            continuation_token=token,
        )

        if not result:
            print("No more reviews found.")
            break

        english_reviews = []

        for review in result:

            review_date = review.get("at")
            review_text = review.get("content", "")

            if review_date < one_year_ago:
                continue

            if is_english(review_text):
                english_reviews.append(
                    {
                        "source": "play_store",
                        "review_text": review_text,
                        "user_rating": review.get("score"),
                        "review_date": review_date,
                    }
                )

        all_reviews.extend(english_reviews)

        print(
            f"Collected English Reviews: "
            f"{len(all_reviews)}"
        )

        oldest_review = min(
            r["at"] for r in result
        )

        if oldest_review < one_year_ago:
            print("Reached reviews older than 1 year.")
            break

        time.sleep(1)

    return all_reviews[:SCRAPE_LIMIT]

def parse_appstore_review(entry):
    review_text = entry.get(
        "content",
        {}
    ).get("label", "")

    user_rating = entry.get(
        "im:rating",
        {}
    ).get("label")

    review_date = entry.get(
        "updated",
        {}
    ).get("label")

    if not review_date:
        return None

    try:
        review_date = datetime.fromisoformat(
            review_date.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except ValueError:
        return None

    try:
        user_rating = int(user_rating)
    except (TypeError, ValueError):
        user_rating = None

    return {
        "source": "app_store",
        "review_text": review_text,
        "user_rating": user_rating,
        "review_date": review_date,
    }


def fetch_appstore_reviews_page(page):
    url = (
        "https://itunes.apple.com/"
        f"{APPSTORE_COUNTRY}/rss/customerreviews/"
        f"page={page}/id={APPSTORE_APP_ID}/"
        "sortBy=mostRecent/json"
    )

    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 CustomerFeedbackIntelligenceAssistant/1.0"
            ),
            "Accept": "application/json",
        },
        timeout=30,
    )

    response.raise_for_status()

    try:
        payload = response.json()
    except json.JSONDecodeError as e:
        preview = response.text[:120].replace("\n", " ")
        raise ValueError(
            "Apple RSS returned a non-JSON response: "
            f"{preview}"
        ) from e

    entries = payload.get(
        "feed",
        {}
    ).get("entry", [])

    if isinstance(entries, dict):
        entries = [entries]

    # The first page often includes app metadata as the first entry.
    return [
        entry for entry in entries
        if "im:rating" in entry
    ]


def scrape_appstore_reviews():
    one_year_ago = datetime.now() - timedelta(days=365)
    collected = []

    print("\nFetching App Store reviews...")

    max_pages = min(
        APPSTORE_MAX_PAGES,
        max(
            1,
            (SCRAPE_LIMIT + APPSTORE_PAGE_SIZE - 1) // APPSTORE_PAGE_SIZE
        )
    )

    for page in range(1, max_pages + 1):
        if len(collected) >= SCRAPE_LIMIT:
            break

        try:
            entries = fetch_appstore_reviews_page(page)
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if status_code == 400 and page > APPSTORE_MAX_PAGES:
                break

            print(f"App Store page {page} fetch failed: {e}")
            break
        except Exception as e:
            print(f"App Store page {page} fetch failed: {e}")
            break

        if not entries:
            break

        page_reviews = []

        for entry in entries:
            review = parse_appstore_review(entry)

            if not review:
                continue

            if review["review_date"] < one_year_ago:
                continue

            if not is_english(review["review_text"]):
                continue

            page_reviews.append(review)

        collected.extend(page_reviews)

        print(
            "Collected App Store reviews: "
            f"{len(collected)}"
        )

        oldest_page_review = min(
            (
                review["review_date"]
                for review in page_reviews
            ),
            default=None,
        )

        if oldest_page_review and oldest_page_review < one_year_ago:
            break

        time.sleep(1)

    collected = collected[:SCRAPE_LIMIT]

    if not collected:
        print(
            "App Store reviews were not collected. "
            "Apple may be rate-limiting or returning no RSS reviews."
        )

    return collected

def create_dataframe(raw_reviews):

    df = pd.DataFrame(raw_reviews)

    df["review_date"] = (
        pd.to_datetime(
            df["review_date"]
        )
        .dt.strftime("%Y-%m-%d")
    )

    return df


def create_final_dataset(df):

    play_df = df[
        df["source"] == "play_store"
    ]

    app_df = df[
        df["source"] == "app_store"
    ]

    play_df = play_df.sample(
        n=min(
            TARGET_PLAYSTORE,
            len(play_df)
        ),
        random_state=42
    )

    app_df = app_df.sample(
        n=min(
            TARGET_APPSTORE,
            len(app_df)
        ),
        random_state=42
    )

    final_df = pd.concat(
        [
            play_df,
            app_df
        ],
        ignore_index=True
    )

    final_df = final_df.sample(
        frac=1,
        random_state=42
    )

    final_df["review_id"] = [
        f"review_{i+1:06d}"
        for i in range(
            len(final_df)
        )
    ]

    return final_df[
        [
            "review_id",
            "source",
            "user_rating",
            "review_text",
            "category",
            "review_date",
            "sentiment",
            "quality_score"
        ]
    ]


def main():

    print("Scraping English reviews...")

    play_reviews = scrape_playstore_reviews()
    app_reviews = scrape_appstore_reviews()
    raw_reviews = play_reviews + app_reviews

    print(f"\nPlay Store Reviews: {len(play_reviews)}")
    print(f"App Store Reviews: {len(app_reviews)}")
    print(f"Combined Reviews: {len(raw_reviews)}")

    df = create_dataframe(raw_reviews)

    print(f"Reviews available for classification: {len(df)}")

    df = classify_dataframe(df)
    df = df[df["quality_score"] >= 4].copy()

    print(f"High quality reviews: {len(df)}")

    df.to_csv("instagram_reviews_full.csv", index=False)

    final_df = create_final_dataset(df)

    final_df.to_csv("instagram_reviews_rag_200.csv", index=False)

    print(
        "\nSaved: instagram_reviews_full.csv"
    )

    print(
        "Saved: instagram_reviews_rag_200.csv"
    )

    print(
        "\nCategory Distribution:"
    )

    print(
        final_df["category"].value_counts()
    )

    print(
        "\nSentiment Distribution:"
    )

    print(
        final_df["sentiment"].value_counts()
    )
    print(
    "\nSource Distribution:"
    )

    print(
        final_df["source"].value_counts()
    )


if __name__ == "__main__":
    main()
