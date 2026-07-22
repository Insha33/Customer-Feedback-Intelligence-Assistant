"use client";

import { MessageSquareTextIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";
import { SUGGESTED_QUESTIONS } from "@/lib/reviewlens-chat";

interface EmptyChatProps {
  composer: ReactNode;
  onSelect: (question: string) => void;
}

export function EmptyChat({ composer, onSelect }: EmptyChatProps) {
  return (
    <section className="flex min-h-full w-full min-w-0 flex-col items-center justify-center overflow-hidden px-4 py-8 text-center md:px-5 md:py-10">
      <span className="grid size-12 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_10px_30px_rgba(49,87,213,0.18)]">
        <MessageSquareTextIcon className="size-5" />
      </span>
      <h2 className="mt-5 text-balance text-[clamp(28px,4vw,42px)] font-semibold leading-[1.08] tracking-[-0.035em] text-foreground">
        What do you need to understand?
      </h2>
      <p className="mt-3 max-w-[620px] text-pretty text-[15px] leading-6 text-muted-foreground">
        Ask about patterns, severity, product priorities, or a specific issue.
        ReviewLens will retrieve and rank the most relevant evidence.
      </p>
      <div className="mt-6 w-full max-w-[760px]">{composer}</div>
      <div className="mt-4 w-full max-w-[760px] overflow-hidden">
        <Suggestions className="justify-start px-1">
          {SUGGESTED_QUESTIONS.map((question) => (
            <Suggestion
              className="h-10 border-border bg-white px-4 text-[13px] font-medium shadow-none hover:border-primary/30 hover:bg-accent hover:text-accent-foreground"
              key={question}
              onClick={onSelect}
              suggestion={question}
            />
          ))}
        </Suggestions>
      </div>
    </section>
  );
}
