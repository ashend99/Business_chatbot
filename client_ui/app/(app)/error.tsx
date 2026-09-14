"use client";

import { Button } from "@/components/ui/Button";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-sm text-center">
        <h2 className="text-base font-semibold text-text-primary">
          Something went wrong
        </h2>
        <p className="mt-1.5 text-[13px] text-text-muted">
          {error.message || "Couldn't load this page."}
        </p>
        <Button variant="secondary" size="sm" onClick={reset} className="mt-4">
          Try again
        </Button>
      </div>
    </div>
  );
}
