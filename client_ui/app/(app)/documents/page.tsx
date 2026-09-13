import { redirect } from "next/navigation";

import { DocumentsView } from "@/components/documents/DocumentsView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { listDocuments } from "@/lib/documents";
import type { DocumentStatus } from "@/lib/types";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function DocumentsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const expiredOnly = sp.expired === "true";
  const status = !expiredOnly && typeof sp.status === "string" ? (sp.status as DocumentStatus) : undefined;

  let data:
    | { ok: true; list: Awaited<ReturnType<typeof listDocuments>> }
    | { ok: false; message: string };
  try {
    const list = await listDocuments({ status, expiredOnly });
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
        : "Something went wrong loading the knowledge base.";
    data = { ok: false, message };
  }

  if (!data.ok) {
    return (
      <>
        <Topbar title="Knowledge base" />
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      </>
    );
  }

  return <DocumentsView documents={data.list.items} total={data.list.total} />;
}
