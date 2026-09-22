"use client";

import { useRouter } from "next/navigation";

import { BuildingIcon, LogoutIcon } from "@/components/icons";

export function Sidebar() {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface px-3 py-5">
      <div className="flex items-center gap-2 px-2 pb-6 pt-1.5">
        <div className="h-[26px] w-[26px] rounded-[7px] bg-accent" />
        <span className="text-[15px] font-semibold text-text-primary">Helalien Admin</span>
      </div>

      <nav className="flex flex-col gap-0.5">
        <span className="flex items-center gap-2.5 rounded-lg bg-accent-soft px-2.5 py-2 text-[13.5px] font-medium text-accent">
          <BuildingIcon size={17} />
          Tenants
        </span>
      </nav>

      <div className="mt-auto flex flex-col gap-0.5">
        <div className="flex items-center gap-2.5 border-t border-border-subtle px-2 pt-2.5">
          <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-soft-fg">
            PA
          </div>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-[12.5px] font-medium text-text-primary">Platform Admin</span>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="ml-auto rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-alt hover:text-text-primary"
          >
            <LogoutIcon size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
