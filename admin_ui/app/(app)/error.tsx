"use client";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
      <p className="text-sm text-text-muted">Something went wrong: {error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="rounded-lg border border-border px-3 py-1.5 text-[12.5px] text-text-secondary hover:bg-surface-alt"
      >
        Try again
      </button>
    </div>
  );
}
