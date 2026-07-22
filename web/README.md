# ReviewLens Ask AI

This directory contains the React and Next.js frontend for ReviewLens Ask AI. It uses Vercel AI Elements for the conversation, messages, prompt input, retrieval trace, evidence sources, and suggested questions.

Run `npm run dev` for UI development or `npm run build` to generate the static bundle served by `backend/reviewlens_server.py`. Local development expects `NEXT_PUBLIC_REVIEWLENS_CHAT_API` to point to the Python streaming endpoint; see `.env.example`.
