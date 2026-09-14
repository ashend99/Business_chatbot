"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { NAV_ITEMS, SETTINGS_NAV, isActive } from "@/lib/nav";

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  badge,
}: {
  href: string;
  label: string;
  icon: (props: { size?: number }) => React.ReactNode;
  active: boolean;
  badge?: number;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors ${
        active
          ? "bg-accent-soft font-medium text-accent"
          : "text-text-secondary hover:bg-surface-alt"
      }`}
    >
      <span className={active ? "text-accent" : "text-text-secondary"}>
        <Icon size={17} />
      </span>
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span className="ml-auto rounded-full bg-accent-soft px-1.5 text-[11px] font-semibold text-accent">
          {badge}
        </span>
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
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
        <span className="text-[15px] font-semibold text-text-primary">Helalien</span>
      </div>

      <nav className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.href}
            {...item}
            active={isActive(pathname, item.href)}
          />
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-0.5">
        <NavLink {...SETTINGS_NAV} active={isActive(pathname, SETTINGS_NAV.href)} />
        <div className="mt-2 flex items-center gap-2.5 border-t border-border-subtle px-2 pt-2.5">
          <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-soft-fg">
            DK
          </div>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-[12.5px] font-medium text-text-primary">
              Dula&apos;s Kitchen
            </span>
            <span className="text-[11px] text-text-muted">Free plan</span>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            className="ml-auto rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-alt hover:text-text-primary"
          >
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <path d="M16 17l5-5-5-5M21 12H9" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
