import io
import json
import re
import unittest
from types import SimpleNamespace

from backend.reviewlens_ai_stream import (
    StreamingChatDependencies,
    retrieval_question,
    structured_question,
    stream_chat_response,
)
from backend.reviewlens_structured_query import (
    RatingFilter,
    StructuredQueryPlan,
    StructuredQueryResult,
)


class FakeHandler:
    def __init__(self):
        self.close_connection = False
        self.headers = []
        self.status = None
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name.lower(), value))

    def end_headers(self):
        pass


def model_chunk(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
    )


def build_dependencies():
    review = {
        "id": "review-1",
        "payload": {
            "review_id": "review-1",
            "category": "Account Suspension",
            "sentiment": "negative",
            "source": "app_store",
            "review_date": "2026-07-01",
            "review_text": "My account was suspended without an explanation.",
        },
    }
    completions = SimpleNamespace(
        create=lambda **_kwargs: iter(
            [model_chunk("Evidence-backed "), model_chunk("answer.")]
        )
    )
    openrouter = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return StreamingChatDependencies(
        get_openai_client=lambda: object(),
        get_openrouter_client=lambda: openrouter,
        get_qdrant_client=lambda: object(),
        run_structured_query=lambda _question: None,
        embed_query=lambda _client, _question: [0.1],
        load_qdrant_documents=lambda _client: [review],
        dense_search=lambda _client, _vector: [review],
        lexical_search=lambda _question, _docs: [review],
        reciprocal_rank_fusion=lambda _lists, _limit: [review],
        build_context=lambda _docs: "Review context",
        source_summary=lambda doc: doc["payload"],
        build_user_prompt=lambda question, context, analytics: (
            f"{question}\n{context}\n{analytics}"
        ),
        system_prompt="Use retrieved evidence only.",
        chat_model="test/model",
        retrieval_limit=6,
        greeting_pattern=re.compile(r"^hi$", re.IGNORECASE),
    )


def parse_stream(handler):
    events = []
    for line in handler.wfile.getvalue().decode("utf-8").splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        events.append(json.loads(line.removeprefix("data: ")))
    return events


class ReviewLensAIStreamTests(unittest.TestCase):
    def test_stream_uses_official_ui_message_protocol(self):
        handler = FakeHandler()
        stream_chat_response(
            handler,
            {
                "messages": [
                    {
                        "id": "user-1",
                        "role": "user",
                        "parts": [
                            {
                                "type": "text",
                                "text": "What causes account suspensions?",
                            }
                        ],
                    }
                ]
            },
            build_dependencies(),
        )

        events = parse_stream(handler)
        event_types = [event["type"] for event in events]
        self.assertEqual(handler.status, 200)
        self.assertIn(
            ("x-vercel-ai-ui-message-stream", "v1"),
            handler.headers,
        )
        self.assertEqual(event_types[0], "start")
        self.assertIn("data-rag-step", event_types)
        self.assertIn("source-document", event_types)
        self.assertIn("text-start", event_types)
        self.assertIn("text-delta", event_types)
        self.assertIn("text-end", event_types)
        self.assertEqual(event_types[-1], "finish")
        self.assertTrue(
            handler.wfile.getvalue().decode("utf-8").endswith(
                "data: [DONE]\n\n"
            )
        )

    def test_source_event_contains_review_evidence(self):
        handler = FakeHandler()
        stream_chat_response(
            handler,
            {"question": "What causes account suspensions?"},
            build_dependencies(),
        )

        source = next(
            event
            for event in parse_stream(handler)
            if event["type"] == "source-document"
        )
        self.assertEqual(source["sourceId"], "review:review-1")
        self.assertEqual(
            source["providerMetadata"]["reviewlens"]["sentiment"],
            "negative",
        )

    def test_greeting_skips_retrieval_services(self):
        dependencies = build_dependencies()
        dependencies = StreamingChatDependencies(
            **{
                **dependencies.__dict__,
                "get_openai_client": lambda: self.fail(
                    "Greeting should not call embeddings"
                ),
            }
        )
        handler = FakeHandler()
        stream_chat_response(handler, {"question": "Hi"}, dependencies)

        text = "".join(
            event.get("delta", "")
            for event in parse_stream(handler)
            if event["type"] == "text-delta"
        )
        self.assertIn("Ask me about customer pain points", text)

    def test_structured_review_list_skips_unfiltered_retrieval(self):
        dependencies = build_dependencies()
        positive_review = {
            "id": "review-4",
            "payload": {
                "review_id": "review-4",
                "user_rating": 4,
                "sentiment": "positive",
                "review_text": "Messaging works reliably.",
            },
        }
        structured_result = StructuredQueryResult(
            plan=StructuredQueryPlan(
                intent="list_reviews",
                sentiment="positive",
                rating=RatingFilter(minimum=4),
                limit=6,
            ),
            analytics_context="Scope filters: sentiment=positive, rating>=4",
            documents=[positive_review],
        )
        dependencies = StreamingChatDependencies(
            **{
                **dependencies.__dict__,
                "run_structured_query": lambda _question: structured_result,
                "get_openai_client": lambda: self.fail(
                    "Structured list should not call embeddings"
                ),
                "get_qdrant_client": lambda: self.fail(
                    "Structured list should not call Qdrant"
                ),
                "get_openrouter_client": lambda: self.fail(
                    "Structured list should not call a chat model"
                ),
            }
        )

        handler = FakeHandler()
        stream_chat_response(
            handler,
            {"question": "Mention top reviews with 4+ ratings and positive sentiment"},
            dependencies,
        )

        sources = [
            event
            for event in parse_stream(handler)
            if event["type"] == "source-document"
        ]
        self.assertEqual(len(sources), 1)
        metadata = sources[0]["providerMetadata"]["reviewlens"]
        self.assertEqual(metadata["user_rating"], 4)
        self.assertEqual(metadata["sentiment"], "positive")

    def test_filtered_semantic_query_ranks_only_structured_candidates(self):
        dependencies = build_dependencies()
        filtered_review = {
            "id": "review-low",
            "payload": {
                "review_id": "review-low",
                "user_rating": 1,
                "sentiment": "negative",
                "review_text": "Login repeatedly fails.",
            },
        }
        structured_result = StructuredQueryResult(
            plan=StructuredQueryPlan(
                intent="semantic_search",
                sentiment="negative",
                rating=RatingFilter(maximum=2),
            ),
            analytics_context="Scope filters: sentiment=negative, rating<=2",
            documents=[filtered_review],
            applied_filters=("sentiment=negative", "rating<=2"),
        )
        dependencies = StreamingChatDependencies(
            **{
                **dependencies.__dict__,
                "run_structured_query": lambda _question: structured_result,
                "lexical_search": lambda _question, docs: docs,
                "get_openai_client": lambda: self.fail(
                    "Filtered semantic search should not call embeddings"
                ),
                "get_qdrant_client": lambda: self.fail(
                    "Filtered semantic search should not call Qdrant"
                ),
            }
        )

        handler = FakeHandler()
        stream_chat_response(
            handler,
            {"question": "Why do low-rated negative reviews mention login?"},
            dependencies,
        )

        sources = [
            event
            for event in parse_stream(handler)
            if event["type"] == "source-document"
        ]
        self.assertEqual([source["sourceId"] for source in sources], ["review:review-low"])
        analytics_step = next(
            event["data"]
            for event in parse_stream(handler)
            if event.get("type") == "data-rag-step"
            and event["data"]["stepId"] == "analytics"
            and event["data"]["status"] == "complete"
        )
        self.assertIn("sentiment=negative", analytics_step["description"])
        self.assertIn("rating<=2", analytics_step["description"])

    def test_unstructured_semantic_query_uses_hybrid_retrieval(self):
        calls = {"embedding": 0, "qdrant": 0, "dense": 0, "lexical": 0}
        dependencies = build_dependencies()

        def count(name, result):
            def call(*_args):
                calls[name] += 1
                return result

            return call

        review = dependencies.load_qdrant_documents(object())[0]
        dependencies = StreamingChatDependencies(
            **{
                **dependencies.__dict__,
                "get_openai_client": count("embedding", object()),
                "get_qdrant_client": count("qdrant", object()),
                "load_qdrant_documents": lambda _client: [review],
                "dense_search": count("dense", [review]),
                "lexical_search": count("lexical", [review]),
            }
        )

        handler = FakeHandler()
        stream_chat_response(
            handler,
            {"question": "Why are users reporting account suspensions?"},
            dependencies,
        )

        self.assertEqual(
            calls,
            {"embedding": 1, "qdrant": 1, "dense": 1, "lexical": 1},
        )

    def test_self_contained_aggregate_does_not_inherit_previous_filters(self):
        captured_questions = []
        dependencies = build_dependencies()
        aggregate_result = StructuredQueryResult(
            plan=StructuredQueryPlan(
                intent="aggregate",
                aggregation="count",
                rating=RatingFilter(minimum=4),
            ),
            analytics_context="Scope filters: rating>=4",
            documents=[],
            applied_filters=("rating>=4",),
            metrics={
                "matching_reviews": 32,
                "total_reviews": 549,
                "average_rating": 4.91,
            },
        )

        def run_structured_query(question):
            captured_questions.append(question)
            return aggregate_result

        dependencies = StreamingChatDependencies(
            **{
                **dependencies.__dict__,
                "run_structured_query": run_structured_query,
                "get_openrouter_client": lambda: self.fail(
                    "Exact counts should not call a chat model"
                ),
                "get_openai_client": lambda: self.fail(
                    "Exact counts should not call embeddings"
                ),
                "get_qdrant_client": lambda: self.fail(
                    "Exact counts should not call Qdrant"
                ),
            }
        )
        messages = [
            {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": "Mention top reviews with positive sentiment",
                    }
                ],
            },
            {
                "role": "assistant",
                "parts": [{"type": "text", "text": "Here are six reviews."}],
            },
            {
                "role": "user",
                "parts": [
                    {"type": "text", "text": "How many 4+ ratings are present?"}
                ],
            },
        ]

        handler = FakeHandler()
        stream_chat_response(handler, {"messages": messages}, dependencies)

        self.assertEqual(captured_questions, ["How many 4+ ratings are present?"])
        answer = "".join(
            event.get("delta", "")
            for event in parse_stream(handler)
            if event["type"] == "text-delta"
        )
        self.assertEqual(answer, "There are **32 reviews** matching rating>=4.")

    def test_referential_follow_up_can_reuse_previous_question(self):
        messages = [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "Show positive reviews"}],
            },
            {
                "role": "assistant",
                "parts": [{"type": "text", "text": "Here they are."}],
            },
            {
                "role": "user",
                "parts": [{"type": "text", "text": "How many of those?"}],
            },
        ]
        self.assertEqual(
            structured_question("How many of those?", messages),
            "Show positive reviews\nFollow-up: How many of those?",
        )

    def test_short_follow_up_reuses_previous_user_question(self):
        messages = [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "What is the top issue?"}],
            },
            {
                "role": "assistant",
                "parts": [{"type": "text", "text": "Account suspension."}],
            },
            {"role": "user", "parts": [{"type": "text", "text": "Why?"}]},
        ]
        self.assertEqual(
            retrieval_question("Why?", messages),
            "What is the top issue?\nFollow-up: Why?",
        )


if __name__ == "__main__":
    unittest.main()
