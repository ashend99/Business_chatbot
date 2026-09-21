import { CurrencyProvider } from "@/components/CurrencyProvider";
import { Sidebar } from "@/components/Sidebar";
import { getSettings } from "@/lib/settings";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  // Best effort: a failed/unauthenticated fetch just falls back to USD here --
  // each page still does its own auth redirect on its own API calls.
  const currency = await getSettings()
    .then((r) => r.capabilities.currency_code)
    .catch(() => "USD");

  return (
    <CurrencyProvider currency={currency}>
      <div className="flex h-screen overflow-hidden bg-bg">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
      </div>
    </CurrencyProvider>
  );
}
