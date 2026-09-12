import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class StockStatus(Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNLIMITED = "unlimited"


class Category(TenantScopedMixin, Base):
    __tablename__ = "categories"

    # self-referencing, unlimited depth; cycle prevention is app-layer only
    # (see repos/catalog.py:reparent_category) -- not enforceable as a DB constraint
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CategoryAttribute(TenantScopedMixin, Base):
    """A reusable variant-building block attached to a category -- e.g.
    "Pizza" defining a "Size" attribute with choices [Small, Medium, Large].
    Every product placed in this category (or a descendant category) can
    offer this attribute when generating its variants; see
    repos/catalog.py's get_effective_attributes for the inheritance walk.
    This is the whole reuse mechanism -- deliberately no separate
    "product template" entity, since the category tree already gives every
    product a natural place to inherit from."""

    __tablename__ = "category_attributes"

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    choices: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Product(TenantScopedMixin, Base):
    __tablename__ = "products"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class Variant(TenantScopedMixin, Base):
    """Every sellable item is a variant row -- including "standalone"
    products, which get exactly one variant auto-created. Keeps price/stock/
    SKU on one table instead of duplicating those fields on Product too."""

    __tablename__ = "variants"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock_status: Mapped[StockStatus] = mapped_column(
        SAEnum(StockStatus, name="stock_status"), default=StockStatus.IN_STOCK, nullable=False
    )
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # custom message shown when out of stock, e.g. "back in 2 weeks"
    stock_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Which attribute choice this variant represents, e.g. {"Size": "Large"}
    # -- display-only provenance from the category-attribute picker; `name`
    # stays the source of truth everywhere else (bot search, lead matching).
    # Manually-added variants simply leave this null.
    attribute_values: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
