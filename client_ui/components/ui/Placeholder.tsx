import { Topbar } from "@/components/Topbar";

/** Temporary stand-in for pages not yet built. */
export function Placeholder({ title }: { title: string }) {
  return (
    <>
      <Topbar title={title} />
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-text-muted">{title} — coming next.</p>
      </div>
    </>
  );
}
