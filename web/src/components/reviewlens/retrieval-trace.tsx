import {
  ChartNoAxesCombinedIcon,
  ListFilterIcon,
  SearchIcon,
  SparklesIcon,
} from "lucide-react";
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import type { RagStep } from "@/lib/reviewlens-chat";

const STEP_ICONS = {
  analytics: ChartNoAxesCombinedIcon,
  answer: SparklesIcon,
  question: ListFilterIcon,
  ranking: ListFilterIcon,
  retrieval: SearchIcon,
};

interface RetrievalTraceProps {
  isStreaming: boolean;
  steps: RagStep[];
}

export function RetrievalTrace({
  isStreaming,
  steps,
}: RetrievalTraceProps) {
  return (
    <ChainOfThought
      className="mb-4 rounded-2xl border border-border bg-[#fafbff] p-4"
      defaultOpen={isStreaming}
    >
      <ChainOfThoughtHeader className="font-medium text-muted-foreground">
        How this answer was built
      </ChainOfThoughtHeader>
      <ChainOfThoughtContent>
        {steps.map((step) => (
          <ChainOfThoughtStep
            description={step.description}
            icon={STEP_ICONS[step.stepId as keyof typeof STEP_ICONS]}
            key={step.stepId}
            label={step.label}
            status={step.status}
          />
        ))}
      </ChainOfThoughtContent>
    </ChainOfThought>
  );
}
