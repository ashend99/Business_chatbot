import { Skeleton, TopbarSkeleton } from "@/components/ui/Skeleton";

export default function LeadsLoading() {
  return (
    <>
      <TopbarSkeleton title="Leads" />
      <div className="flex items-center gap-2 border-b border-border bg-surface px-7 py-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-7 w-20" />
        ))}
        <Skeleton className="ml-auto h-8 w-52" />
      </div>
      <div className="flex-1 overflow-hidden p-5">
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="h-[26px] w-[26px] rounded-full" />
              <Skeleton className="h-4 w-48" />
              <Skeleton className="ml-auto h-5 w-16" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
