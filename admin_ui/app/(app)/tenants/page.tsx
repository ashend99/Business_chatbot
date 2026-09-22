import { redirect } from "next/navigation";

import { Topbar } from "@/components/Topbar";
import { TenantsView } from "@/components/tenants/TenantsView";
import { ApiError } from "@/lib/api";
import { TENANT_PAGE_SIZE } from "@/lib/constants";
import { listTenants } from "@/lib/tenants";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function str(v: string | string[] | undefined): string | undefined {
  return typeof v === "string" && v !== "" ? v : undefined;
}

export default async function TenantsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page) || 1);
  const status = str(sp.status);

  let data:
    | { ok: true; list: Awaited<ReturnType<typeof listTenants>> }
    | { ok: false; message: string };
  try {
    const list = await listTenants({
      isActive: status === "active" ? true : status === "suspended" ? false : undefined,
      search: str(sp.search),
      page,
      pageSize: TENANT_PAGE_SIZE,
    });
    data = { ok: true, list };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
      redirect("/login");
    }
    const message =
      e instanceof ApiError
        ? e.status === 0
          ? "Can't reach the server. Check that the API is running."
          : `The server returned an error (${e.status}).`
        : "Something went wrong loading tenants.";
    data = { ok: false, message };
  }

  return (
    <>
      <Topbar title="Tenants" />
      {data.ok ? (
        <TenantsView tenants={data.list.items} total={data.list.total} page={data.list.page} />
      ) : (
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      )}
    </>
  );
}
