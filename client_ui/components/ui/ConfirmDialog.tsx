"use client";

/**
 * In-dashboard replacement for `window.confirm()` — browsers render the
 * native dialog as a page-chrome banner (with an "example.com says" prefix),
 * which looks like a system message, not part of the app. This renders a
 * themed modal instead, exposed via `useConfirm()`.
 *
 * Usage: `const confirm = useConfirm(); if (!(await confirm("Delete this?"))) return;`
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";

type ConfirmOptions = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Styles the confirm button as a destructive action (red). */
  danger?: boolean;
};

type ConfirmFn = (options: ConfirmOptions | string) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within <ConfirmProvider>");
  return ctx;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);

  const confirm = useCallback<ConfirmFn>((options) => {
    const opts = typeof options === "string" ? { message: options } : options;
    return new Promise<boolean>((resolve) => {
      setPending({ ...opts, resolve });
    });
  }, []);

  function close(result: boolean) {
    pending?.resolve(result);
    setPending(null);
  }

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close(false);
          }}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-label={pending.title ?? "Confirm"}
            className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-xl"
          >
            {pending.title && (
              <h2 className="mb-1.5 text-[15px] font-semibold text-text-primary">{pending.title}</h2>
            )}
            <p className="text-[13px] text-text-secondary">{pending.message}</p>
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => close(false)}>
                {pending.cancelLabel ?? "Cancel"}
              </Button>
              <Button
                type="button"
                autoFocus
                variant={pending.danger ? "danger" : "primary"}
                size="sm"
                onClick={() => close(true)}
              >
                {pending.confirmLabel ?? "Confirm"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
