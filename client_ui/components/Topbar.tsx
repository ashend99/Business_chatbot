import { BellIcon, SearchIcon } from "@/components/icons";
import { ThemeMenu } from "@/components/ThemeMenu";

export function Topbar({ title, actions }: { title: string; actions?: React.ReactNode }) {
  return (
    <header className="flex h-[60px] shrink-0 items-center justify-between border-b border-border bg-surface px-7">
      <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      <div className="flex items-center gap-3.5">
        {actions}
        <div className="flex w-56 items-center gap-2 rounded-lg bg-surface-alt px-3 py-1.5">
          <SearchIcon size={14} className="text-text-muted" />
          <input
            type="search"
            placeholder="Search leads, docs…"
            className="w-full bg-transparent text-[12.5px] text-text-primary placeholder:text-text-muted focus:outline-none"
          />
        </div>
        <button
          type="button"
          aria-label="Notifications"
          className="text-text-secondary transition-colors hover:text-text-primary"
        >
          <BellIcon size={18} />
        </button>
        <ThemeMenu />
      </div>
    </header>
  );
}
