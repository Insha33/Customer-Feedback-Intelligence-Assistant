import { DatabaseIcon, ShieldCheckIcon } from "lucide-react";

export function ChatContext() {
  return (
    <aside className="hidden min-h-0 flex-col border-r border-border bg-[#f8faff] p-7 lg:flex">
      <span className="w-fit rounded-full bg-accent px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-accent-foreground">
        Ask AI
      </span>
      <h1 className="mt-5 max-w-[260px] text-[42px] font-semibold leading-[1.04] tracking-[-0.035em] text-foreground">
        Investigate customer feedback.
      </h1>
      <p className="mt-4 max-w-[280px] text-[15px] leading-6 text-muted-foreground">
        Ask a product question and trace the answer back to retrieved reviews.
      </p>

      <div className="mt-8 grid gap-3 border-y border-border py-5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-primary">
          Active source
        </span>
        <strong className="text-sm font-semibold text-foreground">
          Instagram app reviews
        </strong>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <DatabaseIcon className="size-3.5" /> Qdrant evidence index
        </span>
      </div>

      <div className="mt-auto rounded-2xl border border-[#d7dff6] bg-white/80 p-4">
        <span className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <ShieldCheckIcon className="size-4 text-primary" /> Grounded responses
        </span>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          The retrieval trace shows system operations—not private model
          reasoning.
        </p>
      </div>
    </aside>
  );
}
