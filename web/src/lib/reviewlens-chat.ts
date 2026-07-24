import type { UIMessage } from "ai";

export type RagStepStatus = "complete" | "active" | "pending";

export interface RagStep {
  stepId: string;
  label: string;
  description: string;
  status: RagStepStatus;
}

export interface ReviewSource {
  review_id?: string;
  category?: string;
  sentiment?: string;
  source?: string;
  review_date?: string;
  review_text?: string;
}

export type ReviewLensDataParts = {
  "rag-step": RagStep;
};

export type ReviewLensMessage = UIMessage<unknown, ReviewLensDataParts>;
export type ReviewSourcePart = Extract<
  ReviewLensMessage["parts"][number],
  { type: "source-document" }
>;

export const CHAT_API =
  process.env.NEXT_PUBLIC_REVIEWLENS_CHAT_API ?? "/api/chat/stream";

export const SUGGESTED_QUESTIONS = [
  "What are the top three product problems users mention most?",
  "What should we prioritize in the next sprint?",
  "Why are users reporting account suspensions?",
  "Which issues are support gaps rather than engineering bugs?",
];

export function getRagSteps(message: ReviewLensMessage): RagStep[] {
  return message.parts.flatMap((part) =>
    part.type === "data-rag-step" ? [part.data] : [],
  );
}

export function getSourceParts(
  message: ReviewLensMessage,
): ReviewSourcePart[] {
  return message.parts.flatMap((part) =>
    part.type === "source-document" ? [part] : [],
  );
}

export function getSourceMetadata(
  source: ReviewSourcePart,
): ReviewSource | undefined {
  const metadata = source.providerMetadata?.reviewlens;
  if (!metadata || typeof metadata !== "object") {
    return undefined;
  }
  return metadata as ReviewSource;
}
