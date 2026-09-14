import "server-only";

import { apiFetch } from "@/lib/api";
import type { CategoryAttribute, CategoryTreeNode, Product, ProductWithVariants } from "@/lib/types";

export function getCategoryTree(): Promise<CategoryTreeNode[]> {
  return apiFetch<CategoryTreeNode[]>("/tenant/categories/tree");
}

export function getEffectiveAttributes(categoryId: string): Promise<CategoryAttribute[]> {
  return apiFetch<CategoryAttribute[]>(`/tenant/categories/${categoryId}/effective-attributes`);
}

export function listProducts(categoryId?: string): Promise<Product[]> {
  const q = categoryId ? `?category_id=${categoryId}` : "";
  return apiFetch<Product[]>(`/tenant/products${q}`);
}

export function getProduct(id: string): Promise<ProductWithVariants> {
  return apiFetch<ProductWithVariants>(`/tenant/products/${id}`);
}
