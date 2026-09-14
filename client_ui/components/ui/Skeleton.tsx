export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-alt ${className}`} />;
}

/** Topbar-shaped placeholder so `loading.tsx` matches the page frame. */
export function TopbarSkeleton({ title }: { title: string }) {
  return (
    <div className="flex h-[60px] shrink-0 items-center justify-between border-b border-border bg-surface px-7">
      <span className="text-base font-semibold text-text-primary">{title}</span>
      <Skeleton className="h-8 w-56" />
    </div>
  );
}
