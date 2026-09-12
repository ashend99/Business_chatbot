"use client";

import { useEffect, useRef } from "react";

export function Modal({
  title,
  onClose,
  children,
  width = 420,
  height,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  width?: number;
  /** Fixed height in px — the dialog stays this size regardless of content,
   * and the body scrolls internally. Omit to size to content (up to 85vh). */
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{ width, height }}
        className={`flex flex-col rounded-2xl border border-border bg-surface shadow-xl ${
          height ? "overflow-hidden" : "max-h-[85vh] overflow-auto p-5"
        }`}
      >
        <div
          className={`flex shrink-0 items-center justify-between ${height ? "border-b border-border-subtle px-5 py-4" : "mb-4"}`}
        >
          <h2 className="text-[15px] font-semibold text-text-primary">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-text-muted hover:bg-surface-alt hover:text-text-primary"
          >
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        {height ? <div className="flex-1 overflow-y-auto p-5">{children}</div> : children}
      </div>
    </div>
  );
}
