import type { ChatStatus } from "ai";
import {
  PromptInput,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";

const GUIDED_PROMPTS = [
  "What are the top three product problems users mention most?",
  "What should we prioritize in the next sprint?",
  "Which issues are support gaps rather than engineering bugs?",
];

interface ChatComposerProps {
  error?: Error;
  input: string;
  isStreaming: boolean;
  onInputChange: (value: string) => void;
  onStop: () => void;
  onSubmit: (message: PromptInputMessage) => void;
  status: ChatStatus;
}

export function ChatComposer({
  error,
  input,
  isStreaming,
  onInputChange,
  onStop,
  onSubmit,
  status,
}: ChatComposerProps) {
  return (
    <div className="w-full">
      {error ? (
        <p className="mb-2 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">
          {error.message}
        </p>
      ) : null}
      <PromptInput
        className="w-full rounded-full focus-within:[&_[data-slot=input-group]]:border-primary/35 focus-within:[&_[data-slot=input-group]]:bg-white focus-within:[&_[data-slot=input-group]]:shadow-[0_0_0_3px_rgba(49,87,213,0.10),0_10px_32px_rgba(23,32,51,0.08)] [&_[data-slot=input-group]]:min-h-[62px] [&_[data-slot=input-group]]:rounded-[31px] [&_[data-slot=input-group]]:border [&_[data-slot=input-group]]:border-transparent [&_[data-slot=input-group]]:bg-secondary [&_[data-slot=input-group]]:px-1.5 [&_[data-slot=input-group]]:opacity-100! [&_[data-slot=input-group]]:shadow-[0_8px_26px_rgba(23,32,51,0.07)] [&_[data-slot=input-group]]:transition-[border-color,background-color,box-shadow] [&_[data-slot=input-group]]:duration-200"
        onSubmit={onSubmit}
      >
        <PromptInputActionMenu>
          <PromptInputActionMenuTrigger
            className="ml-1 size-10 shrink-0 rounded-full text-muted-foreground hover:bg-white hover:text-foreground"
            tooltip="Add a guided prompt"
          />
          <PromptInputActionMenuContent className="w-72 rounded-2xl p-2">
            {GUIDED_PROMPTS.map((prompt) => (
              <PromptInputActionMenuItem
                className="cursor-pointer rounded-xl px-3 py-2.5 text-[13px] leading-5"
                key={prompt}
                onSelect={() => onInputChange(prompt)}
              >
                {prompt}
              </PromptInputActionMenuItem>
            ))}
          </PromptInputActionMenuContent>
        </PromptInputActionMenu>
        <PromptInputTextarea
          aria-label="Ask about your customer feedback"
          className="max-h-36 min-h-[58px] px-2 py-[17px] text-[15px] leading-6 placeholder:text-[#8a95a8] sm:px-3"
          onChange={(event) => onInputChange(event.currentTarget.value)}
          placeholder="Ask anything about your customer feedback"
          value={input}
        />
        <PromptInputSubmit
          className="mr-1 size-10 shrink-0 rounded-full border-0 bg-primary text-primary-foreground opacity-100! shadow-none hover:bg-[#2445b3] disabled:bg-primary disabled:text-primary-foreground"
          disabled={!isStreaming && !input.trim()}
          onStop={onStop}
          status={status}
        />
      </PromptInput>
    </div>
  );
}
