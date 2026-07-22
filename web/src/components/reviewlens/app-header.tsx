export function AppHeader() {
  return (
    <header className="z-20 flex h-[68px] shrink-0 items-center border-b border-border bg-white/95 px-5 backdrop-blur-xl md:px-10">
      <div className="mx-auto grid w-full max-w-[1440px] grid-cols-[1fr_auto_1fr] items-center">
        <a
          className="flex w-fit items-center gap-3 text-foreground no-underline"
          href="/frontend/"
        >
          <span className="grid size-9 place-items-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground">
            R
          </span>
          <span className="hidden text-[15px] font-semibold tracking-[-0.015em] sm:block">
            ReviewLens
            <small className="block text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Feedback intelligence
            </small>
          </span>
        </a>

        <nav
          aria-label="Primary navigation"
          className="flex rounded-full border border-border bg-secondary p-1"
        >
          <a className="nav-pill" href="/frontend/">
            Overview
          </a>
          <a className="nav-pill" href="/frontend/backlog.html">
            Backlog
          </a>
          <a
            aria-current="page"
            className="nav-pill bg-primary text-primary-foreground hover:bg-primary"
            href="/frontend/chat-app/"
          >
            Ask AI
          </a>
        </nav>
        <span className="hidden justify-self-end text-xs font-medium text-muted-foreground lg:block">
          Answers include review evidence
        </span>
      </div>
    </header>
  );
}
