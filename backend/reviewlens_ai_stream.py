from dataclasses import dataclass
from typing import Any, Callable, Pattern

from .reviewlens_ai_protocol import (
    ClientDisconnected,
    UIMessageStreamWriter,
    message_text,
    parse_chat_request,
)


MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_TEXT = 1200


@dataclass(frozen=True)
class StreamingChatDependencies:
    get_openai_client: Callable[[], Any]
    get_openrouter_client: Callable[[], Any]
    get_qdrant_client: Callable[[], Any]
    structured_analytics_context: Callable[[str], str | None]
    embed_query: Callable[[Any, str], list[float]]
    load_qdrant_documents: Callable[[Any], list[dict[str, Any]]]
    dense_search: Callable[[Any, list[float]], list[dict[str, Any]]]
    lexical_search: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]
    reciprocal_rank_fusion: Callable[
        [list[list[dict[str, Any]]], int], list[dict[str, Any]]
    ]
    build_context: Callable[[list[dict[str, Any]]], str]
    source_summary: Callable[[dict[str, Any]], dict[str, Any]]
    build_user_prompt: Callable[[str, str, str | None], str]
    system_prompt: str
    chat_model: str
    retrieval_limit: int
    greeting_pattern: Pattern[str]


def conversation_context(messages):
    transcript = []
    for message in messages[:-1][-MAX_HISTORY_MESSAGES:]:
        if not isinstance(message, dict) or message.get("role") not in {
            "user",
            "assistant",
        }:
            continue
        text = message_text(message)
        if text:
            transcript.append(
                f"{message['role'].title()}: {text[:MAX_HISTORY_TEXT]}"
            )
    return "\n".join(transcript)


def contextual_question(question, messages):
    history = conversation_context(messages)
    if not history:
        return question
    return f"Previous conversation:\n{history}\n\nCurrent question:\n{question}"


def retrieval_question(question, messages):
    if len(question.split()) >= 8:
        return question
    previous_questions = [
        message_text(message)
        for message in messages[:-1]
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    if not previous_questions or not previous_questions[-1]:
        return question
    return f"{previous_questions[-1]}\nFollow-up: {question}"


def stream_model_answer(writer, dependencies, question, docs, analytics_context):
    context = dependencies.build_context(docs)
    user_prompt = dependencies.build_user_prompt(
        question,
        context,
        analytics_context,
    )
    response = dependencies.get_openrouter_client().chat.completions.create(
        model=dependencies.chat_model,
        messages=[
            {"role": "system", "content": dependencies.system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        stream=True,
    )
    received_text = False
    for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        received_text = True
        writer.text_delta(delta)
    if not received_text:
        raise RuntimeError("The model completed without returning answer text.")


def stream_rag_answer(writer, question, messages, dependencies):
    writer.rag_step(
        "question",
        "Question understood",
        "Prepared the request for evidence retrieval.",
        "complete",
    )
    if dependencies.greeting_pattern.fullmatch(question):
        writer.text_delta(
            "**Hello!** Ask me about customer pain points, recurring themes, "
            "issue severity, or what to prioritize next."
        )
        return

    search_question = retrieval_question(question, messages)
    prompt_question = contextual_question(question, messages)
    writer.rag_step(
        "analytics",
        "Checking product metrics",
        "Looking for counts, ratings, and category-level evidence.",
        "active",
    )
    analytics_context = dependencies.structured_analytics_context(search_question)
    writer.rag_step(
        "analytics",
        "Product metrics checked",
        (
            "Relevant structured metrics were added to the answer context."
            if analytics_context
            else "This question does not require structured metrics."
        ),
        "complete",
    )

    writer.rag_step(
        "retrieval",
        "Searching customer feedback",
        "Running semantic and keyword retrieval across indexed reviews.",
        "active",
    )
    openai_client = dependencies.get_openai_client()
    qdrant_client = dependencies.get_qdrant_client()
    query_vector = dependencies.embed_query(openai_client, search_question)
    docs = dependencies.load_qdrant_documents(qdrant_client)
    dense_results = dependencies.dense_search(qdrant_client, query_vector)
    lexical_results = dependencies.lexical_search(search_question, docs)
    writer.rag_step(
        "retrieval",
        "Customer feedback searched",
        (
            f"Found {len(dense_results)} semantic and "
            f"{len(lexical_results)} keyword candidates."
        ),
        "complete",
    )

    writer.rag_step(
        "ranking",
        "Ranking the evidence",
        "Combining both result sets and selecting the strongest reviews.",
        "active",
    )
    fused_docs = dependencies.reciprocal_rank_fusion(
        [dense_results, lexical_results],
        dependencies.retrieval_limit,
    )
    writer.rag_step(
        "ranking",
        "Evidence ranked",
        f"Selected {len(fused_docs)} reviews for the grounded response.",
        "complete",
    )
    for doc in fused_docs:
        writer.source_document(dependencies.source_summary(doc))

    if not fused_docs and not analytics_context:
        writer.text_delta(
            "I could not find matching reviews in the current Qdrant collection."
        )
        return

    writer.rag_step(
        "answer",
        "Writing the answer",
        "Synthesizing the selected evidence into a concise recommendation.",
        "active",
    )
    stream_model_answer(
        writer,
        dependencies,
        prompt_question,
        fused_docs,
        analytics_context,
    )
    writer.rag_step(
        "answer",
        "Answer grounded",
        "The response is linked to the retrieved evidence shown below.",
        "complete",
    )


def stream_chat_response(handler, payload, dependencies):
    writer = UIMessageStreamWriter(handler)
    writer.open()
    try:
        question, messages = parse_chat_request(payload)
        stream_rag_answer(writer, question, messages, dependencies)
        writer.finish()
    except ClientDisconnected:
        return
    except Exception as error:
        try:
            writer.error(str(error))
        except ClientDisconnected:
            return
