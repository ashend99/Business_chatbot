"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AddProductModal } from "@/components/catalog/AddProductModal";
import { CategoryTree } from "@/components/catalog/CategoryTree";
import { ProductDetailPanel } from "@/components/catalog/ProductDetailPanel";
import { PlusIcon } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Topbar } from "@/components/Topbar";
import type { CategoryTreeNode, Product } from "@/lib/types";

export function CatalogView({
  tree,
  products,
}: {
  tree: CategoryTreeNode[];
  products: Product[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selectedCategoryId = params.get("category");
  const selectedProductId = params.get("product");

  const [addOpen, setAddOpen] = useState(false);

  function closeProduct() {
    const next = new URLSearchParams(params.toString());
    next.delete("product");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function openProduct(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("product", id);
    router.push(`${pathname}?${next}`);
    router.refresh(); // pick up the newly created product/category in the tree
  }

  return (
    <>
      <Topbar
        title="Catalog"
        actions={
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <PlusIcon size={14} />
            Add product
          </Button>
        }
      />
      <div className="flex flex-1 overflow-hidden">
        <CategoryTree tree={tree} products={products} />

        {selectedProductId ? (
          <ProductDetailPanel
            key={selectedProductId}
            productId={selectedProductId}
            tree={tree}
            onClose={closeProduct}
            onDeleted={() => {
              closeProduct();
              router.refresh();
            }}
          />
        ) : (
          <div className="flex h-full min-w-0 flex-1 items-center justify-center border-l border-border bg-surface">
            <p className="text-sm text-text-muted">No product is selected</p>
          </div>
        )}
      </div>

      {addOpen && (
        <AddProductModal
          tree={tree}
          defaultCategoryId={selectedCategoryId}
          onClose={() => setAddOpen(false)}
          onCreated={openProduct}
        />
      )}
    </>
  );
}
