import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import reviewlens_server
from backend.reviewlens_ai_stream import StreamingChatDependencies, stream_chat_response
from backend.reviewlens_server import ReviewLensHandler
from backend.reviewlens_structured_query import (
    format_aggregate_answer,
    parse_structured_query,
)
from test_reviewlens_ai_stream import FakeHandler, build_dependencies, parse_stream


class ReviewLensServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewLensHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=5,
        )
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        headers = {
            name.lower(): value for name, value in response.getheaders()
        }
        connection.close()
        return response.status, headers, body

    def test_root_serves_dashboard_with_root_asset_paths(self):
        status, _headers, body = self.request("/")

        self.assertEqual(status, 200)
        self.assertIn(b'href="/styles.css?', body)
        self.assertIn(b'src="/app.js?', body)

    def test_root_stylesheet_is_served(self):
        status, headers, body = self.request("/styles.css")

        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/css"))
        self.assertIn(b":root", body)

    def test_health_reports_request_scoped_sqlite_connections(self):
        status, _headers, body = self.request("/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(body)["sqlite_connection_scope"],
            "request",
        )

    def test_backlog_serves_page_with_canonical_links(self):
        status, _headers, body = self.request("/backlog")

        self.assertEqual(status, 200)
        self.assertIn(b'href="/backlog"', body)
        self.assertIn(b'src="/backlog.js?', body)

    def test_old_frontend_routes_redirect_to_canonical_paths(self):
        status, headers, _body = self.request("/frontend/")
        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], "/")

        status, headers, _body = self.request("/frontend/backlog.html")
        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], "/backlog")

    def test_structured_analytics_supports_concurrent_request_threads(self):
        def reset_sql_cache():
            with reviewlens_server.SQL_CACHE_LOCK:
                reviewlens_server.SQL_CACHE.update(
                    {"mtime": None, "rows": [], "categories": []}
                )

        csv_content = "\n".join(
            [
                "review_id,source,user_rating,review_text,category,review_date,sentiment,quality_score",
                "1,app_store,1,Locked out,Account Access,2026-07-01,negative,0.9",
                "2,play_store,5,Works well,Usability,2026-07-02,positive,0.8",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "reviews.csv"
            csv_path.write_text(csv_content, encoding="utf-8")

            with patch.object(reviewlens_server, "REVIEW_CSV", csv_path):
                reset_sql_cache()
                self.addCleanup(reset_sql_cache)

                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(
                        executor.map(
                            reviewlens_server.structured_analytics_context,
                            ["What is the sentiment split?"] * 16,
                        )
                    )

        self.assertTrue(
            all("- Matching reviews: 2 of 2 (100%)" in result for result in results)
        )

    def test_structured_query_parses_rating_ranges_and_review_limit(self):
        plan = parse_structured_query(
            "Mention the top 3 reviews with 4+ ratings and positive sentiments",
            [],
        )

        self.assertEqual(plan.intent, "list_reviews")
        self.assertEqual(plan.sentiment, "positive")
        self.assertEqual(plan.rating.minimum, 4)
        self.assertTrue(plan.rating.minimum_inclusive)
        self.assertEqual(plan.limit, 3)

        plan = parse_structured_query("Show reviews below 3 stars", [])
        self.assertEqual(plan.rating.maximum, 3)
        self.assertFalse(plan.rating.maximum_inclusive)

        plan = parse_structured_query("List reviews between 2 and 4 stars", [])
        self.assertEqual(plan.rating.minimum, 2)
        self.assertEqual(plan.rating.maximum, 4)

        plan = parse_structured_query("Why do 1-star reviews mention login?", [])
        self.assertEqual(plan.intent, "semantic_search")

        plan = parse_structured_query("How many positive reviews have at least 4 stars?", [])
        self.assertEqual(plan.intent, "aggregate")
        self.assertEqual(plan.aggregation, "count")
        self.assertEqual(plan.sentiment, "positive")
        self.assertEqual(plan.rating.minimum, 4)

        plan = parse_structured_query(
            "Show positive reviews\nFollow-up: How many of those?",
            [],
        )
        self.assertEqual(plan.intent, "aggregate")
        self.assertEqual(plan.aggregation, "count")
        self.assertEqual(plan.sentiment, "positive")

        plan = parse_structured_query(
            "Show positive reviews\nFollow-up: How many negative ones?",
            [],
        )
        self.assertEqual(plan.sentiment, "negative")

    def test_metric_requests_take_priority_over_review_list_wording(self):
        for question, aggregation in (
            ("give me percentage of negative reviews", "percentage"),
            ("Show me the percent of positive reviews", "percentage"),
            ("Give me the share of neutral reviews", "percentage"),
            ("Give me the count of negative reviews", "count"),
            ("Show the average rating of negative reviews", "average"),
            ("Show negative reviews\nFollow-up: give me percentage of those reviews", "percentage"),
        ):
            with self.subTest(question=question):
                plan = parse_structured_query(question, [])
                self.assertEqual(plan.intent, "aggregate")
                self.assertEqual(plan.aggregation, aggregation)

        for question in (
            "Give me negative reviews",
            "Show reviews about account suspension",
            "List reviews mentioning discounts",
        ):
            with self.subTest(question=question):
                self.assertEqual(parse_structured_query(question, []).intent, "list_reviews")

    def test_negative_percentage_returns_sql_answer_without_examples(self):
        def reset_sql_cache():
            with reviewlens_server.SQL_CACHE_LOCK:
                reviewlens_server.SQL_CACHE.update(
                    {"mtime": None, "rows": [], "categories": []}
                )

        question = "give me percentage of negative reviews"
        csv_content = "\n".join([
            "review_id,source,user_rating,review_text,category,review_date,sentiment,quality_score",
            "one,app_store,5,Excellent,General,2026-07-01,positive,0.9",
            "two,play_store,4,Useful,General,2026-07-02,positive,0.8",
            "three,play_store,3,Fine,General,2026-07-03,neutral,0.7",
            "four,app_store,5,Account suspended,Login,2026-07-04,negative,1.0",
        ])
        expected = "**1 of 4 reviews (25.0%)** match sentiment=negative."
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "reviews.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            with patch.object(reviewlens_server, "REVIEW_CSV", csv_path):
                reset_sql_cache()
                self.addCleanup(reset_sql_cache)
                with patch.object(reviewlens_server, "get_openai_client", side_effect=AssertionError("Unexpected embeddings")), patch.object(reviewlens_server, "get_openrouter_client", side_effect=AssertionError("Unexpected LLM")):
                    response = reviewlens_server.handle_chat(question)
                self.assertEqual(response["answer"], expected)
                self.assertEqual(response["sources"], [])
                self.assertEqual(response["retrieval"]["mode"], "structured_sql_only")

                dependencies = StreamingChatDependencies(**{
                    **build_dependencies().__dict__,
                    "run_structured_query": reviewlens_server.run_structured_query,
                    "get_openai_client": lambda: self.fail("Unexpected embeddings"),
                    "get_openrouter_client": lambda: self.fail("Unexpected LLM"),
                    "get_qdrant_client": lambda: self.fail("Unexpected vector search"),
                })
                handler = FakeHandler()
                stream_chat_response(handler, {"question": question}, dependencies)
                events = parse_stream(handler)
                answer = "".join(event["delta"] for event in events if event["type"] == "text-delta")
                self.assertEqual(answer, expected)
                self.assertFalse(any(event["type"] == "source-document" for event in events))

    def test_structured_review_query_returns_only_filtered_sorted_rows(self):
        def reset_sql_cache():
            with reviewlens_server.SQL_CACHE_LOCK:
                reviewlens_server.SQL_CACHE.update(
                    {"mtime": None, "rows": [], "categories": []}
                )

        csv_content = "\n".join(
            [
                "review_id,source,user_rating,review_text,category,review_date,sentiment,quality_score",
                "one,app_store,5,Excellent experience,General,2026-07-01,positive,0.7",
                "two,play_store,4,Useful features,Features,2026-07-02,positive,0.9",
                "three,play_store,3,Mostly fine,General,2026-07-03,positive,1.0",
                "four,app_store,5,Broken login,Login,2026-07-04,negative,1.0",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "reviews.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            with patch.object(reviewlens_server, "REVIEW_CSV", csv_path):
                reset_sql_cache()
                self.addCleanup(reset_sql_cache)
                result = reviewlens_server.run_structured_query(
                    "Mention the top reviews with 4+ ratings and positive sentiments"
                )

        self.assertEqual(result.plan.intent, "list_reviews")
        self.assertEqual(
            [doc["id"] for doc in result.documents],
            ["one", "two"],
        )
        self.assertIn("rating>=4", result.analytics_context)
        self.assertIn("sentiment=positive", result.analytics_context)
        self.assertTrue(
            all(
                doc["payload"]["user_rating"] >= 4
                and doc["payload"]["sentiment"] == "positive"
                for doc in result.documents
            )
        )

    def test_exact_aggregate_answers_use_filtered_sql_metrics(self):
        def reset_sql_cache():
            with reviewlens_server.SQL_CACHE_LOCK:
                reviewlens_server.SQL_CACHE.update(
                    {"mtime": None, "rows": [], "categories": []}
                )

        csv_content = "\n".join(
            [
                "review_id,source,user_rating,review_text,category,review_date,sentiment,quality_score",
                "one,app_store,5,Excellent,General,2026-07-01,positive,0.9",
                "two,play_store,4,Useful,Features,2026-07-02,positive,0.8",
                "three,play_store,3,Fine,General,2026-07-03,neutral,0.7",
                "four,app_store,1,Broken,Login,2026-07-04,negative,1.0",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "reviews.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            with patch.object(reviewlens_server, "REVIEW_CSV", csv_path):
                reset_sql_cache()
                self.addCleanup(reset_sql_cache)

                count_result = reviewlens_server.run_structured_query(
                    "How many 4+ ratings are present?"
                )
                percentage_result = reviewlens_server.run_structured_query(
                    "What percentage of reviews have 4+ ratings?"
                )
                average_result = reviewlens_server.run_structured_query(
                    "What is the average rating for positive reviews?"
                )

        self.assertEqual(
            format_aggregate_answer(count_result),
            "There are **2 reviews** matching rating>=4.",
        )
        self.assertEqual(
            format_aggregate_answer(percentage_result),
            "**2 of 4 reviews (50.0%)** match rating>=4.",
        )
        self.assertEqual(
            format_aggregate_answer(average_result),
            "The average rating is **4.50/5** across 2 reviews matching sentiment=positive.",
        )


if __name__ == "__main__":
    unittest.main()
