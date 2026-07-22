import json
import uuid


class ClientDisconnected(Exception):
    pass


class UIMessageStreamWriter:
    def __init__(self, handler):
        self.handler = handler
        self.message_id = f"msg_{uuid.uuid4().hex}"
        self.text_id = f"text_{uuid.uuid4().hex}"
        self.text_started = False

    def open(self):
        self.handler.send_response(200)
        self.handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.handler.send_header("Cache-Control", "no-cache, no-store")
        self.handler.send_header("Connection", "close")
        self.handler.send_header("x-vercel-ai-ui-message-stream", "v1")
        self.handler.end_headers()
        self.handler.close_connection = True
        self.write({"type": "start", "messageId": self.message_id})

    def write(self, part):
        payload = json.dumps(part, ensure_ascii=False, separators=(",", ":"))
        try:
            self.handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise ClientDisconnected from error

    def rag_step(self, step_id, label, description, status):
        self.write(
            {
                "type": "data-rag-step",
                "id": f"rag-step-{step_id}",
                "data": {
                    "stepId": step_id,
                    "label": label,
                    "description": description,
                    "status": status,
                },
            }
        )

    def source_document(self, source):
        review_id = str(source.get("review_id") or "unknown")
        category = source.get("category") or "Customer feedback"
        self.write(
            {
                "type": "source-document",
                "sourceId": f"review:{review_id}",
                "mediaType": "text/plain",
                "title": f"Review {review_id} · {category}",
                "providerMetadata": {"reviewlens": source},
            }
        )

    def text_delta(self, delta):
        if not self.text_started:
            self.write({"type": "text-start", "id": self.text_id})
            self.text_started = True
        self.write({"type": "text-delta", "id": self.text_id, "delta": delta})

    def finish(self):
        if self.text_started:
            self.write({"type": "text-end", "id": self.text_id})
        self.write({"type": "finish"})
        self.done()

    def error(self, message):
        self.write({"type": "error", "errorText": message})
        self.write({"type": "finish"})
        self.done()

    def done(self):
        try:
            self.handler.wfile.write(b"data: [DONE]\n\n")
            self.handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise ClientDisconnected from error


def message_text(message):
    parts = message.get("parts") or []
    text_parts = [
        part.get("text", "")
        for part in parts
        if part.get("type") == "text" and isinstance(part.get("text"), str)
    ]
    if text_parts:
        return "\n".join(text_parts).strip()
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def parse_chat_request(payload):
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise ValueError("Messages must be an array.")

    user_messages = [
        message
        for message in messages
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    question = message_text(user_messages[-1]) if user_messages else ""
    if not question:
        question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("Question is required.")
    return question, messages
