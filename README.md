# ReviewLens

ReviewLens turns customer feedback from multiple channels into evidence-backed product priorities. The dashboard summarizes the current review set, the backlog ranks recommended actions, and Ask AI lets product teams investigate themes through a grounded RAG conversation.

## Run the product

Install the Python and web dependencies, then start the integrated server:

```bash
uv sync
npm --prefix web install
npm run start:dashboard
```

The npm scripts automatically find `uv` in your `PATH`, `~/.local/bin`, or
`~/.cargo/bin`. If it is not installed, use `brew install uv` on macOS or one
of the official installation methods linked in the error message.

Open:

- Dashboard: `http://127.0.0.1:8080/frontend/`
- Ask AI: `http://127.0.0.1:8080/frontend/chat-app/`

`start:dashboard` refreshes the backlog when possible, builds the static Next.js chat application, and serves both experiences from the Python server.

For chat UI development with hot reload, copy `web/.env.example` to `web/.env.local`, run `npm run dev:chat`, and keep `reviewlens_server.py` running on port 8080.

## Ask AI architecture

- The frontend is a React 19 and Next.js application built with official Vercel AI Elements components.
- `useChat` and `DefaultChatTransport` send AI SDK UI messages to `/api/chat/stream`.
- The Python endpoint preserves the existing OpenAI embeddings, Qdrant hybrid retrieval, structured analytics, reciprocal-rank fusion, and OpenRouter answer generation.
- The endpoint streams the AI SDK data protocol: retrieval status data parts, review sources, text deltas, completion, and `[DONE]`.
- The interface labels the expandable status panel as a retrieval trace. It exposes system operations and never private model chain-of-thought.

The legacy `/api/chat` JSON endpoint remains available for compatibility.

## Configuration

The server reads configuration from environment variables or the repository `.env` file. Ask AI requires:

- `OPENAI_API_KEY` for embeddings
- `OPENROUTER_API_KEY` for answer generation
- `QDRANT_URL` or `QDRANT_CLUSTER_ENDPOINT`
- `QDRANT_API_KEY` when required by the configured cluster

Optional variables include `OPENROUTER_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `QDRANT_COLLECTION`, `REVIEWLENS_CORS_ORIGIN`, and the retrieval-limit settings defined in `reviewlens_server.py`.

## Verify

```bash
UV_CACHE_DIR=/private/tmp/reviewlens-uv-cache \
  uv run python -m unittest test_reviewlens_ai_stream.py test_rag_ingestion.py
npm --prefix web run lint
npm --prefix web run build
```

The stream tests use local fakes, so they validate protocol order, source metadata, follow-up retrieval, and the greeting path without sending review data to an external model.
