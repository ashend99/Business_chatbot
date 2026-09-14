import { Skeleton, TopbarSkeleton } from "@/components/ui/Skeleton";

export default function DocumentsLoading() {
  return (
    <>
      <TopbarSkeleton title="Knowledge base" />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col gap-3 border-r border-border p-5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-24" />
          ))}
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={`row-${i}`} className="h-10 w-full" />
          ))}
        </div>
        <div className="flex min-w-0 flex-1 items-center justify-center">
          <Skeleton className="h-40 w-2/3" />
        </div>
      </div>
    </>
  );
}
