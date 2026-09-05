import uuid
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.models.catalog import StockStatus


class CategoryCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class CategoryReparentRequest(BaseModel):
    parent_id: uuid.UUID | None = None


class CategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int

    model_config = {"from_attributes": True}


class CategoryTreeNode(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    children: list["CategoryTreeNode"] = []


class VariantCreate(BaseModel):
    name: str
    sku: str | None = None
    price: Decimal
    stock_status: StockStatus = StockStatus.IN_STOCK
    stock_qty: int | None = None
    stock_message: str | None = None


class VariantUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    stock_status: StockStatus | None = None
    stock_qty: int | None = None
    stock_message: str | None = None
    active: bool | None = None


class VariantRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    sku: str | None
    price: Decimal
    stock_status: StockStatus
    stock_qty: int | None
    stock_message: str | None
    active: bool

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    """Either supply `variants` explicitly, or leave it empty and supply
    `price` (+ optional sku/stock fields) directly on the product -- that
    flat data becomes the single auto-created default variant, named after
    the product. The plan's "auto-creates one default variant if none
    supplied" needs a price from somewhere; this is that somewhere."""

    name: str
    category_id: uuid.UUID | None = None
    description: str | None = None
    image_url: str | None = None
    variants: list[VariantCreate] = []

    price: Decimal | None = None
    sku: str | None = None
    stock_status: StockStatus = StockStatus.IN_STOCK
    stock_qty: int | None = None
    stock_message: str | None = None

    @model_validator(mode="after")
    def _require_price_for_standalone(self) -> "ProductCreate":
        if not self.variants and self.price is None:
            raise ValueError("price is required when creating a product without explicit variants")
        return self


class ProductUpdate(BaseModel):
    name: str | None = None
    category_id: uuid.UUID | None = None
    description: str | None = None
    image_url: str | None = None


class ProductRead(BaseModel):
    id: uuid.UUID
    name: str
    category_id: uuid.UUID | None
    description: str | None
    image_url: str | None

    model_config = {"from_attributes": True}


class ProductWithVariants(ProductRead):
    variants: list[VariantRead] = []


class CatalogSearchResult(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    category_name: str | None
    price: Decimal
    stock_status: StockStatus
    stock_qty: int | None
    stock_message: str | None
