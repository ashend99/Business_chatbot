import { Skeleton } from "@/components/ui/Skeleton";

export default function AppLoading() {
  return (
    <>
      <div className="h-[60px] shrink-0 border-b border-border bg-surface" />
      <div className="flex-1 p-7">
        <Skeleton className="h-64 w-full" />
      </div>
    </>
  );
}
