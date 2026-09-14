import { redirect } from "next/navigation";

import { OrdersView } from "@/components/orders/OrdersView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { listOrders } from "@/lib/orders";
import type { OrderStatus } from "@/lib/types";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function OrdersPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const status = typeof sp.status === "string" ? (sp.status as OrderStatus) : undefined;

  let data:
    | { ok: true; list: Awaited<ReturnType<typeof listOrders>> }
    | { ok: false; message: string };
  try {
    const list = await listOrders({ status });
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
        : "Something went wrong loading orders.";
    data = { ok: false, message };
  }

  if (!data.ok) {
    return (
      <>
        <Topbar title="Orders" />
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      </>
    );
  }

  return <OrdersView orders={data.list.items} total={data.list.total} />;
}
