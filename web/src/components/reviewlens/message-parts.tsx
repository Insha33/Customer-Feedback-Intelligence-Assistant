import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import { EvidenceSources } from "@/components/reviewlens/evidence-sources";
import { RetrievalTrace } from "@/components/reviewlens/retrieval-trace";
import {
  getRagSteps,
  getSourceParts,
  type ReviewLensMessage,
} from "@/lib/reviewlens-chat";

interface MessagePartsProps {
  isLastMessage: boolean;
  isStreaming: boolean;
  message: ReviewLensMessage;
}

const INTERNAL_REVIEW_ID = /[ \t]*\[review[_\s-]*\d+\]/gi;
const LEADING_ANSWER_LABEL = /^\s*(?:\*\*)?answer:(?:\*\*)?\s*/i;

function cleanAssistantText(text: string) {
  return text
    .replace(LEADING_ANSWER_LABEL, "")
    .replace(INTERNAL_REVIEW_ID, "");
}

export function MessageParts({
  isLastMessage,
  isStreaming,
  message,
}: MessagePartsProps) {
  const ragSteps = getRagSteps(message);
  const sources = getSourceParts(message);
  const animateText = isLastMessage && isStreaming;

  return (
    <Message className="max-w-[820px]" from={message.role}>
      <MessageContent className="group-[.is-user]:rounded-2xl group-[.is-user]:bg-secondary group-[.is-user]:px-4 group-[.is-user]:py-3">
        {message.role === "assistant" && ragSteps.length > 0 ? (
          <RetrievalTrace isStreaming={animateText} steps={ragSteps} />
        ) : null}
        {message.parts.map((part, index) =>
          part.type === "text" ? (
            <MessageResponse
              className="text-[15px] leading-7 text-foreground"
              isAnimating={animateText}
              key={`${message.id}-text-${index}`}
            >
              {message.role === "assistant"
                ? cleanAssistantText(part.text)
                : part.text}
            </MessageResponse>
          ) : null,
        )}
        {message.role === "assistant" && sources.length > 0 ? (
          <EvidenceSources sources={sources} />
        ) : null}
      </MessageContent>
    </Message>
  );
}
