import { Skeleton, TopbarSkeleton } from "@/components/ui/Skeleton";

export default function CatalogLoading() {
  return (
    <>
      <TopbarSkeleton title="Catalog" />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-56 shrink-0 flex-col gap-2 border-r border-border p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
        <div className="flex-1 p-5">
          <div className="flex flex-col gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
