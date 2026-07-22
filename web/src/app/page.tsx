import { AppHeader } from "@/components/reviewlens/app-header";
import { ChatWorkspace } from "@/components/reviewlens/chat-workspace";

export default function AskAIPage() {
  return (
    <main className="flex h-dvh min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <AppHeader />
      <ChatWorkspace />
    </main>
  );
}
