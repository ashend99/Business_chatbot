"use client";

import { useEffect, useRef, useState } from "react";

import { ChevronDownIcon, MonitorIcon, MoonIcon, SunIcon } from "@/components/icons";
import { ACCENTS, useTheme, type ThemeMode } from "@/lib/theme";

const MODES: { value: ThemeMode; label: string; icon: (p: { size?: number }) => React.ReactNode }[] =
  [
    { value: "light", label: "Light", icon: SunIcon },
    { value: "dark", label: "Dark", icon: MoonIcon },
    { value: "system", label: "System", icon: MonitorIcon },
  ];

export function ThemeMenu() {
  const { mode, accent, setMode, setAccent } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const ActiveIcon = MODES.find((m) => m.value === mode)?.icon ?? MonitorIcon;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Theme settings"
        className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-text-secondary transition-colors hover:bg-surface-alt"
      >
        <ActiveIcon size={16} />
        <ChevronDownIcon size={12} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-2 w-56 rounded-xl border border-border bg-surface p-3 shadow-lg"
        >
          <p className="px-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Appearance
          </p>
          <div className="flex gap-1">
            {MODES.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`flex flex-1 flex-col items-center gap-1 rounded-lg border px-2 py-2 text-[11px] transition-colors ${
                  mode === value
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-border text-text-secondary hover:bg-surface-alt"
                }`}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </div>

          <p className="px-1 pb-1.5 pt-3 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Accent
          </p>
          <div className="flex gap-2 px-1">
            {ACCENTS.map((a) => (
              <button
                key={a.value}
                type="button"
                onClick={() => setAccent(a.value)}
                aria-label={a.label}
                aria-pressed={accent === a.value}
                className={`h-6 w-6 rounded-full ring-offset-2 ring-offset-surface transition ${
                  accent === a.value ? "ring-2 ring-text-secondary" : ""
                }`}
                style={{ backgroundColor: a.swatch }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
