import io
import json
import re
import unittest
from types import SimpleNamespace

from reviewlens_ai_stream import (
    StreamingChatDependencies,
    retrieval_question,
    stream_chat_response,
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
        structured_analytics_context=lambda _question: "Metrics",
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
