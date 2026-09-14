import type { CategoryTreeNode } from "@/lib/types";

export type FlatCategory = { id: string; name: string; depth: number };

/**
 * Flattens the tree into display order (depth-first, respecting
 * `sort_order`/`name` from the API) with indentation depth — for building a
 * "choose a category" <select>. `excludeSubtreeRootId` drops that node and
 * everything below it, so a category can't be moved under itself or its own
 * descendant (the backend also rejects this; this just keeps the picker from
 * offering an option that would always fail).
 */
export function flattenTree(
  nodes: CategoryTreeNode[],
  depth = 0,
  excludeSubtreeRootId?: string,
): FlatCategory[] {
  const out: FlatCategory[] = [];
  for (const node of nodes) {
    if (node.id === excludeSubtreeRootId) continue;
    out.push({ id: node.id, name: node.name, depth });
    out.push(...flattenTree(node.children, depth + 1, excludeSubtreeRootId));
  }
  return out;
}
