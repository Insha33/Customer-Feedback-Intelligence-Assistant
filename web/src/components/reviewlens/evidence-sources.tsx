import { FileTextIcon } from "lucide-react";
import {
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "@/components/ai-elements/sources";
import {
  getSourceMetadata,
  type ReviewSourcePart,
} from "@/lib/reviewlens-chat";

interface EvidenceSourcesProps {
  sources: ReviewSourcePart[];
}

export function EvidenceSources({ sources }: EvidenceSourcesProps) {
  return (
    <Sources className="mt-5 mb-0 text-primary">
      <SourcesTrigger
        className="rounded-full border border-border bg-white px-3 py-2 transition-colors hover:bg-accent"
        count={sources.length}
      >
        <FileTextIcon className="size-3.5" />
        <span className="font-medium">
          {sources.length} review{sources.length === 1 ? "" : "s"} used
        </span>
      </SourcesTrigger>
      <SourcesContent className="w-full gap-2">
        {sources.map((source) => {
          const metadata = getSourceMetadata(source);
          return (
            <article
              className="rounded-xl border border-border bg-[#fafbff] p-3 text-left"
              key={source.sourceId}
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <strong className="text-xs font-semibold text-foreground">
                  {source.title}
                </strong>
                {metadata?.sentiment ? (
                  <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {metadata.sentiment}
                  </span>
                ) : null}
              </div>
              {metadata?.review_text ? (
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                  {metadata.review_text}
                </p>
              ) : null}
            </article>
          );
        })}
      </SourcesContent>
    </Sources>
  );
}
