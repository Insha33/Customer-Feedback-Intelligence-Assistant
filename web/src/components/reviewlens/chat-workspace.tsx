"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useCallback, useState } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { ChatComposer } from "@/components/reviewlens/chat-composer";
import { ChatContext } from "@/components/reviewlens/chat-context";
import { EmptyChat } from "@/components/reviewlens/empty-chat";
import { MessageParts } from "@/components/reviewlens/message-parts";
import {
  CHAT_API,
  type ReviewLensMessage,
} from "@/lib/reviewlens-chat";

const chatTransport = new DefaultChatTransport<ReviewLensMessage>({
  api: CHAT_API,
});

export function ChatWorkspace() {
  const [input, setInput] = useState("");
  const { error, messages, sendMessage, status, stop } =
    useChat<ReviewLensMessage>({
      transport: chatTransport,
    });
  const isStreaming = status === "submitted" || status === "streaming";

  const submitQuestion = useCallback(
    (question: string) => {
      const text = question.trim();
      if (!text || isStreaming) {
        return;
      }
      void sendMessage({ text });
      setInput("");
    },
    [isStreaming, sendMessage],
  );

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      submitQuestion(message.text);
    },
    [submitQuestion],
  );

  const handleStop = useCallback(() => {
    void stop();
  }, [stop]);

  const composer = (
    <ChatComposer
      error={error}
      input={input}
      isStreaming={isStreaming}
      onInputChange={setInput}
      onStop={handleStop}
      onSubmit={handleSubmit}
      status={status}
    />
  );

  return (
    <section className="min-h-0 min-w-0 flex-1 overflow-hidden p-3 md:p-5">
      <div className="mx-auto grid h-full min-h-0 w-full max-w-[1440px] overflow-hidden rounded-[22px] border border-border bg-white shadow-[0_20px_55px_rgba(23,32,51,0.10)] lg:grid-cols-[320px_minmax(0,1fr)]">
        <ChatContext />
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
            <div className="flex items-center gap-2.5">
              <span className="size-2 rounded-full bg-emerald-600 shadow-[0_0_0_4px_#e5f5f1]" />
              <strong className="text-sm font-semibold text-foreground">
                ReviewLens AI
              </strong>
            </div>
            <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
              Evidence-aware RAG assistant
            </span>
          </div>

          <Conversation className="min-h-0 min-w-0 overflow-x-hidden">
            <ConversationContent className="mx-auto min-h-full min-w-0 w-full max-w-[900px] gap-7 overflow-x-hidden px-4 py-6 md:px-8 md:py-7">
              {messages.length === 0 ? (
                <EmptyChat composer={composer} onSelect={submitQuestion} />
              ) : (
                messages.map((message, index) => (
                  <MessageParts
                    isLastMessage={index === messages.length - 1}
                    isStreaming={isStreaming}
                    key={message.id}
                    message={message}
                  />
                ))
              )}
            </ConversationContent>
            <ConversationScrollButton className="bottom-3 shadow-sm" />
          </Conversation>

          {messages.length > 0 ? (
            <div className="min-w-0 shrink-0 bg-gradient-to-t from-white via-white to-white/85 px-4 pt-3 pb-4 md:px-6">
              <div className="mx-auto w-full max-w-[820px]">{composer}</div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
