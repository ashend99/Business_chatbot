import { redirect } from "next/navigation";

import { CatalogView } from "@/components/catalog/CatalogView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { getCategoryTree, listProducts } from "@/lib/catalog";

export default async function CatalogPage() {
  let data:
    | {
        ok: true;
        tree: Awaited<ReturnType<typeof getCategoryTree>>;
        products: Awaited<ReturnType<typeof listProducts>>;
      }
    | { ok: false; message: string };
  try {
    // Everything (categories and products, at every depth) renders in one
    // tree + detail panel on this single page -- no separate product route.
    const [tree, products] = await Promise.all([getCategoryTree(), listProducts()]);
    data = { ok: true, tree, products };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
      redirect("/login");
    }
    const message =
      e instanceof ApiError
        ? e.status === 0
          ? "Can't reach the server. Check that the API is running."
          : `The server returned an error (${e.status}).`
        : "Something went wrong loading the catalog.";
    data = { ok: false, message };
  }

  if (!data.ok) {
    return (
      <>
        <Topbar title="Catalog" />
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      </>
    );
  }

  return <CatalogView tree={data.tree} products={data.products} />;
}
