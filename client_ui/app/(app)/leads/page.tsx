import { redirect } from "next/navigation";

import { LeadsView } from "@/components/leads/LeadsView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { listLeads } from "@/lib/leads";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function str(v: string | string[] | undefined): string | undefined {
  return typeof v === "string" && v !== "" ? v : undefined;
}

export default async function LeadsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page) || 1);

  let data:
    | { ok: true; list: Awaited<ReturnType<typeof listLeads>> }
    | { ok: false; message: string };
  try {
    const list = await listLeads({
      status: str(sp.status),
      search: str(sp.search),
      createdAfter: str(sp.created_after),
      page,
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
        : "Something went wrong loading leads.";
    data = { ok: false, message };
  }

  return (
    <>
      <Topbar title="Leads" />
      {data.ok ? (
        <LeadsView leads={data.list.items} total={data.list.total} page={data.list.page} />
      ) : (
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      )}
    </>
  );
}
