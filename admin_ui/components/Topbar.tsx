import { ThemeMenu } from "@/components/ThemeMenu";

export function Topbar({ title, actions }: { title: string; actions?: React.ReactNode }) {
  return (
    <header className="flex h-[60px] shrink-0 items-center justify-between border-b border-border bg-surface px-7">
      <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      <div className="flex items-center gap-3.5">
        {actions}
        <ThemeMenu />
      </div>
    </header>
  );
}
