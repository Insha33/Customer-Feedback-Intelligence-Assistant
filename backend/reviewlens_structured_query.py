import re
from dataclasses import dataclass, field
from typing import Any


STRUCTURED_TERMS = (
    "how many",
    "count",
    "percentage",
    "percent",
    "share",
    "average",
    "avg",
    "breakdown",
    "distribution",
    "split",
    "compare",
    "top category",
    "top categories",
    "most common",
    "least common",
)


@dataclass(frozen=True)
class RatingFilter:
    minimum: float | None = None
    minimum_inclusive: bool = True
    maximum: float | None = None
    maximum_inclusive: bool = True

    def sql(self) -> tuple[list[str], list[float], list[str]]:
        clauses = []
        params = []
        labels = []
        if self.minimum is not None:
            operator = ">=" if self.minimum_inclusive else ">"
            clauses.append(f"user_rating {operator} ?")
            params.append(self.minimum)
            labels.append(f"rating{operator}{format_number(self.minimum)}")
        if self.maximum is not None:
            operator = "<=" if self.maximum_inclusive else "<"
            clauses.append(f"user_rating {operator} ?")
            params.append(self.maximum)
            labels.append(f"rating{operator}{format_number(self.maximum)}")
        return clauses, params, labels


@dataclass(frozen=True)
class StructuredQueryPlan:
    intent: str
    aggregation: str | None = None
    sentiment: str | None = None
    source: str | None = None
    category: str | None = None
    rating: RatingFilter | None = None
    limit: int = 6

    @property
    def has_filters(self) -> bool:
        return any((self.sentiment, self.source, self.category, self.rating))


@dataclass(frozen=True)
class StructuredQueryResult:
    plan: StructuredQueryPlan
    analytics_context: str
    documents: list[dict[str, Any]]
    applied_filters: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)


def format_number(value: float) -> str:
    numeric_value = float(value)
    return str(int(numeric_value)) if numeric_value.is_integer() else str(value)


def parse_rating_filter(query: str) -> RatingFilter | None:
    between = re.search(
        r"\bbetween\s+([1-5](?:\.\d+)?)\s+(?:and|to)\s+([1-5](?:\.\d+)?)"
        r"(?:\s*(?:stars?|ratings?))?\b",
        query,
    )
    if between:
        lower, upper = sorted((float(between.group(1)), float(between.group(2))))
        return RatingFilter(minimum=lower, maximum=upper)

    patterns = (
        (
            r"\b([1-5](?:\.\d+)?)\s*\+\s*(?:stars?|ratings?)?\b"
            r"|\b(?:at least|minimum(?: of)?)\s+([1-5](?:\.\d+)?)"
            r"(?:\s*(?:stars?|ratings?))?\b"
            r"|\b([1-5](?:\.\d+)?)\s+(?:stars?|ratings?)?\s*(?:or higher|and above)\b",
            "minimum",
            True,
        ),
        (
            r"\b(?:above|over|more than|greater than)\s+([1-5](?:\.\d+)?)"
            r"(?:\s*(?:stars?|ratings?))?\b",
            "minimum",
            False,
        ),
        (
            r"\b(?:at most|maximum(?: of)?|up to)\s+([1-5](?:\.\d+)?)"
            r"(?:\s*(?:stars?|ratings?))?\b"
            r"|\b([1-5](?:\.\d+)?)\s+(?:stars?|ratings?)?\s*(?:or lower|and below)\b",
            "maximum",
            True,
        ),
        (
            r"\b(?:below|under|less than)\s+([1-5](?:\.\d+)?)"
            r"(?:\s*(?:stars?|ratings?))?\b",
            "maximum",
            False,
        ),
    )
    for pattern, bound, inclusive in patterns:
        match = re.search(pattern, query)
        if match:
            value = float(next(group for group in match.groups() if group))
            if bound == "minimum":
                return RatingFilter(minimum=value, minimum_inclusive=inclusive)
            return RatingFilter(maximum=value, maximum_inclusive=inclusive)

    exact = re.search(
        r"\b([1-5](?:\.\d+)?)\s*-?\s*(?:star|rating)s?\b",
        query,
    )
    if exact:
        value = float(exact.group(1))
        return RatingFilter(minimum=value, maximum=value)
    if any(term in query for term in ("critical", "low rating", "low-rated")):
        return RatingFilter(maximum=2)
    return None


def parse_limit(query: str, default_limit: int) -> int:
    match = re.search(r"\b(?:top|first|last)\s+(\d{1,2})\s+reviews?\b", query)
    if not match:
        return default_limit
    return max(1, min(int(match.group(1)), 20))


def parse_structured_query(
    question: str,
    categories: list[str],
    default_limit: int = 6,
) -> StructuredQueryPlan | None:
    query = (question or "").lower()
    intent_query = query.rsplit("follow-up:", 1)[-1].strip()

    def parse_sentiment(text):
        return next(
            (
                value
                for value in ("negative", "neutral", "positive")
                if value in text
            ),
            None,
        )

    def parse_category(text):
        return next(
            (
                value
                for value in sorted(categories, key=len, reverse=True)
                if value.lower() in text
            ),
            None,
        )

    sentiment = parse_sentiment(intent_query) or parse_sentiment(query)
    category = parse_category(intent_query) or parse_category(query)
    source_aliases = {
        "app_store": ("app store", "ios", "iphone"),
        "play_store": ("play store", "android", "google play"),
        "meta_forum": ("meta forum", "forum", "community forum"),
    }
    def parse_source(text):
        source_mentions = [
            source
            for source, aliases in source_aliases.items()
            if any(alias in text for alias in aliases)
        ]
        comparison = any(
            term in text for term in ("split", "compare", "versus", " vs ")
        )
        if len(source_mentions) == 1 and not comparison:
            return source_mentions[0]
        return None

    source = parse_source(intent_query) or parse_source(query)
    rating = parse_rating_filter(intent_query) or parse_rating_filter(query)
    has_filters = any((sentiment, source, category, rating))
    list_request = bool(
        re.search(
            r"\b(?:show|list|mention|give|find)\b.{0,50}\breviews?\b",
            intent_query,
        )
        or re.search(
            r"\b(?:top|best|worst)(?:\s+\d+)?\s+reviews?\b",
            intent_query,
        )
    )
    aggregate_terms = {
        term
        for term in STRUCTURED_TERMS
        if re.search(r"\b" + re.escape(term) + r"\b", intent_query)
    }
    aggregate_request = bool(aggregate_terms)

    aggregation = None
    if aggregate_terms & {"how many", "count"}:
        aggregation = "count"
    elif aggregate_terms & {"percentage", "percent", "share"}:
        aggregation = "percentage"
    elif aggregate_terms & {"average", "avg"}:
        aggregation = "average"
    elif aggregate_terms & {"breakdown", "distribution", "split"}:
        aggregation = "breakdown"
    elif aggregate_terms & {"top category", "top categories"}:
        aggregation = "category_ranking"
    elif "compare" in aggregate_terms:
        aggregation = "comparison"

    # A metric request can also contain "give/show ... reviews". Resolve the
    # explicit aggregation first so it is not mistaken for review examples.
    if aggregate_request:
        intent = "aggregate"
    elif list_request:
        intent = "list_reviews"
    elif has_filters:
        intent = "semantic_search"
    else:
        return None

    return StructuredQueryPlan(
        intent=intent,
        aggregation=aggregation,
        sentiment=sentiment,
        source=source,
        category=category,
        rating=rating,
        limit=parse_limit(intent_query, default_limit),
    )


def sql_filters(plan: StructuredQueryPlan) -> tuple[list[str], list[Any], list[str]]:
    clauses: list[str] = []
    params: list[Any] = []
    labels: list[str] = []
    for column, value in (
        ("category", plan.category),
        ("sentiment", plan.sentiment),
        ("source", plan.source),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
            labels.append(f"{column}={value}")
    if plan.rating:
        rating_clauses, rating_params, rating_labels = plan.rating.sql()
        clauses.extend(rating_clauses)
        params.extend(rating_params)
        labels.extend(rating_labels)
    return clauses, params, labels


def format_review_list_answer(result: StructuredQueryResult) -> str:
    if not result.documents:
        filters = ", ".join(result.applied_filters) or "the requested filters"
        return f"No reviews matched {filters}."

    filters = ", ".join(result.applied_filters)
    opening = f"Found {len(result.documents)} top matching review"
    if len(result.documents) != 1:
        opening += "s"
    if filters:
        opening += f" for {filters}"
    lines = [opening + ":", "", "**What the reviews show:**"]
    for document in result.documents:
        payload = document["payload"]
        rating = format_number(float(payload.get("user_rating") or 0))
        sentiment = payload.get("sentiment") or "unknown sentiment"
        review_text = str(payload.get("review_text") or "No review text available.")
        if len(review_text) > 280:
            review_text = review_text[:277].rstrip() + "..."
        source = payload.get("source")
        review_date = payload.get("review_date")
        metadata = " · ".join(value for value in (source, review_date) if value)
        suffix = f" _({metadata})_" if metadata else ""
        lines.append(f"- **{rating} stars · {sentiment}** — {review_text}{suffix}")
    return "\n".join(lines)


def format_aggregate_answer(result: StructuredQueryResult) -> str | None:
    aggregation = result.plan.aggregation
    if aggregation not in {"count", "percentage", "average"}:
        return None

    matching = int(result.metrics["matching_reviews"])
    total = int(result.metrics["total_reviews"])
    filters = ", ".join(result.applied_filters) or "all reviews"
    if aggregation == "count":
        noun = "review" if matching == 1 else "reviews"
        return f"There are **{matching} {noun}** matching {filters}."
    if aggregation == "percentage":
        percentage = (matching / total * 100) if total else 0
        return (
            f"**{matching} of {total} reviews ({percentage:.1f}%)** "
            f"match {filters}."
        )

    average_rating = result.metrics.get("average_rating")
    if average_rating is None:
        return f"No reviews matched {filters}, so an average rating is unavailable."
    return (
        f"The average rating is **{average_rating:.2f}/5** across "
        f"{matching} reviews matching {filters}."
    )
