import { redirect } from "next/navigation";

import { SettingsView } from "@/components/settings/SettingsView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { getSettings } from "@/lib/settings";
import type { TenantSettingsResponse } from "@/lib/types";

export default async function SettingsPage() {
  let data: { ok: true; settings: TenantSettingsResponse } | { ok: false; message: string };
  try {
    data = { ok: true, settings: await getSettings() };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
      redirect("/login");
    }
    const message =
      e instanceof ApiError
        ? e.status === 0
          ? "Can't reach the server. Check that the API is running."
          : `The server returned an error (${e.status}).`
        : "Something went wrong loading settings.";
    data = { ok: false, message };
  }

  if (!data.ok) {
    return (
      <>
        <Topbar title="Settings" />
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      </>
    );
  }

  return <SettingsView initial={data.settings} />;
}
