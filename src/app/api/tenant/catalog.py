import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.repos import catalog as catalog_repo
from app.schemas.catalog import (
    CatalogSearchResult,
    CategoryAttributeRead,
    CategoryAttributesReplaceRequest,
    CategoryCreate,
    CategoryRead,
    CategoryReparentRequest,
    CategoryTreeNode,
    CategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductWithVariants,
    VariantCreate,
    VariantRead,
    VariantUpdate,
)

router = APIRouter(prefix="/tenant", tags=["catalog"])


# ---- categories ---------------------------------------------------------


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> CategoryRead:
    category = await catalog_repo.create_category(
        session, tenant_id, name=payload.name, parent_id=payload.parent_id, sort_order=payload.sort_order
    )
    await session.commit()
    return CategoryRead.model_validate(category)


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CategoryRead]:
    categories = await catalog_repo.list_categories(session, tenant_id)
    return [CategoryRead.model_validate(c) for c in categories]


@router.get("/categories/tree", response_model=list[CategoryTreeNode])
async def get_category_tree(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CategoryTreeNode]:
    tree = await catalog_repo.get_category_tree(session, tenant_id)
    return [CategoryTreeNode.model_validate(node) for node in tree]


@router.get("/categories/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> CategoryRead:
    category = await catalog_repo.get_category(session, tenant_id, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    return CategoryRead.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> CategoryRead:
    category = await catalog_repo.update_category(session, tenant_id, category_id, **payload.model_dump(exclude_unset=True))
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    await session.commit()
    return CategoryRead.model_validate(category)


@router.patch("/categories/{category_id}/reparent", response_model=CategoryRead)
async def reparent_category(
    category_id: uuid.UUID,
    payload: CategoryReparentRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> CategoryRead:
    try:
        category = await catalog_repo.reparent_category(session, tenant_id, category_id, payload.parent_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    await session.commit()
    return CategoryRead.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await catalog_repo.delete_category(session, tenant_id, category_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    await session.commit()


# ---- category attributes ---------------------------------------------------
# The reusable variant-building blocks a category offers (e.g. "Pizza" ->
# Size: [Small, Medium, Large]) -- see repos/catalog.py for the inheritance
# rule (a subcategory inherits its ancestors' attributes, overriding by name).


@router.get("/categories/{category_id}/attributes", response_model=list[CategoryAttributeRead])
async def list_category_attributes(
    category_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CategoryAttributeRead]:
    if await catalog_repo.get_category(session, tenant_id, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    attrs = await catalog_repo.list_category_attributes(session, tenant_id, category_id)
    return [CategoryAttributeRead.model_validate(a) for a in attrs]


@router.put("/categories/{category_id}/attributes", response_model=list[CategoryAttributeRead])
async def replace_category_attributes(
    category_id: uuid.UUID,
    payload: CategoryAttributesReplaceRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CategoryAttributeRead]:
    if await catalog_repo.get_category(session, tenant_id, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    attrs = await catalog_repo.replace_category_attributes(
        session, tenant_id, category_id, [a.model_dump() for a in payload.attributes]
    )
    await session.commit()
    return [CategoryAttributeRead.model_validate(a) for a in attrs]


@router.get("/categories/{category_id}/effective-attributes", response_model=list[CategoryAttributeRead])
async def get_effective_attributes(
    category_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CategoryAttributeRead]:
    """This category's own attributes plus everything inherited from its
    ancestors -- what the "add product" flow uses to build the
    checkbox-driven variant generator."""
    if await catalog_repo.get_category(session, tenant_id, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    attrs = await catalog_repo.get_effective_attributes(session, tenant_id, category_id)
    return [CategoryAttributeRead.model_validate(a) for a in attrs]


# ---- products -------------------------------------------------------------


@router.post("/products", response_model=ProductWithVariants, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> ProductWithVariants:
    variant_specs = (
        [v.model_dump() for v in payload.variants]
        if payload.variants
        else [
            {
                "price": payload.price,
                "sku": payload.sku,
                "stock_status": payload.stock_status,
                "stock_qty": payload.stock_qty,
                "stock_message": payload.stock_message,
            }
        ]
    )
    product = await catalog_repo.create_product(
        session,
        tenant_id,
        name=payload.name,
        category_id=payload.category_id,
        description=payload.description,
        image_url=payload.image_url,
        variants=variant_specs,
    )
    variants = await catalog_repo.list_variants_for_product(session, tenant_id, product.id)
    await session.commit()
    return ProductWithVariants(**ProductRead.model_validate(product).model_dump(), variants=[VariantRead.model_validate(v) for v in variants])


@router.get("/products", response_model=list[ProductRead])
async def list_products(
    category_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProductRead]:
    products = await catalog_repo.list_products(session, tenant_id, category_id=category_id)
    return [ProductRead.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductWithVariants)
async def get_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> ProductWithVariants:
    product = await catalog_repo.get_product(session, tenant_id, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    variants = await catalog_repo.list_variants_for_product(session, tenant_id, product_id)
    return ProductWithVariants(**ProductRead.model_validate(product).model_dump(), variants=[VariantRead.model_validate(v) for v in variants])


@router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> ProductRead:
    product = await catalog_repo.update_product(session, tenant_id, product_id, **payload.model_dump(exclude_unset=True))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    await session.commit()
    return ProductRead.model_validate(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await catalog_repo.delete_product(session, tenant_id, product_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    await session.commit()


# ---- variants ---------------------------------------------------------


@router.post("/products/{product_id}/variants", response_model=VariantRead, status_code=status.HTTP_201_CREATED)
async def add_variant(
    product_id: uuid.UUID,
    payload: VariantCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> VariantRead:
    product = await catalog_repo.get_product(session, tenant_id, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")

    variant = await catalog_repo.add_variant(
        session,
        tenant_id,
        product_id,
        name=payload.name,
        sku=payload.sku,
        price=payload.price,
        stock_status=payload.stock_status,
        stock_qty=payload.stock_qty,
        stock_message=payload.stock_message,
    )
    await session.commit()
    return VariantRead.model_validate(variant)


@router.get("/products/{product_id}/variants", response_model=list[VariantRead])
async def list_variants(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[VariantRead]:
    variants = await catalog_repo.list_variants_for_product(session, tenant_id, product_id)
    return [VariantRead.model_validate(v) for v in variants]


@router.patch("/products/{product_id}/variants/{variant_id}", response_model=VariantRead)
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> VariantRead:
    variant = await catalog_repo.update_variant(session, tenant_id, variant_id, **payload.model_dump(exclude_unset=True))
    if variant is None or variant.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    await session.commit()
    return VariantRead.model_validate(variant)


@router.delete("/products/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    variant = await catalog_repo.get_variant(session, tenant_id, variant_id)
    if variant is None or variant.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    await catalog_repo.delete_variant(session, tenant_id, variant_id)
    await session.commit()


# ---- search ---------------------------------------------------------


@router.get("/catalog/search", response_model=list[CatalogSearchResult])
async def search_catalog(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[CatalogSearchResult]:
    rows = await catalog_repo.search_catalog(session, tenant_id, q, limit=limit)
    return [
        CatalogSearchResult(
            variant_id=variant.id,
            product_id=product.id,
            product_name=product.name,
            variant_name=variant.name,
            category_name=category.name if category else None,
            price=variant.price,
            stock_status=variant.stock_status,
            stock_qty=variant.stock_qty,
            stock_message=variant.stock_message,
        )
        for variant, product, category in rows
    ]
