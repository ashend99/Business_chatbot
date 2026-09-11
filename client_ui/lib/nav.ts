import {
  CatalogIcon,
  ConversationsIcon,
  KnowledgeIcon,
  LeadsIcon,
  OverviewIcon,
  SettingsIcon,
} from "@/components/icons";

export type NavItem = {
  href: string;
  label: string;
  icon: (props: { size?: number }) => React.ReactNode;
};

/** Primary nav — order matters, it's the sidebar order. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: OverviewIcon },
  { href: "/leads", label: "Leads", icon: LeadsIcon },
  { href: "/documents", label: "Knowledge base", icon: KnowledgeIcon },
  { href: "/catalog", label: "Catalog", icon: CatalogIcon },
  { href: "/conversations", label: "Conversations", icon: ConversationsIcon },
];

export const SETTINGS_NAV: NavItem = {
  href: "/settings",
  label: "Settings",
  icon: SettingsIcon,
};

/** True when `pathname` is within the section rooted at `href`. */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
