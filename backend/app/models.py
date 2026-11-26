from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Product(Base):
    __tablename__ = "products"

    picnic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_quantity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parsed_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    picnic_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_food: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # produce | protein | whole_food | staple | treat_snack | beverage | household
    bucket: Mapped[str] = mapped_column(String(32), default="staple", nullable=False)

    kcal_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugar_g_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_g_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    nova_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nutriscore_grade: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # pending | rule | openfoodfacts | llm | manual
    enrichment_source: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    enrichment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ignored_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    purchase_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_purchased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    delivery_items: Mapped[list[DeliveryItem]] = relationship(back_populates="product")


class Delivery(Base):
    __tablename__ = "deliveries"

    delivery_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(64), default="COMPLETED", nullable=False)
    delivery_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    iso_week: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    total_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_per_1000_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    fresh_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    nova_1_2_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    snack_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[DeliveryItem]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan"
    )


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("deliveries.delivery_id", ondelete="CASCADE"), nullable=False
    )
    picnic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.picnic_id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    delivery: Mapped[Delivery] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="delivery_items")

    __table_args__ = (
        Index("ix_delivery_items_delivery_id", "delivery_id"),
        Index("ix_delivery_items_picnic_id", "picnic_id"),
    )


class CartSnapshot(Base):
    __tablename__ = "cart_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    total_price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    computed_metrics_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class MealieRecipe(Base):
    __tablename__ = "mealie_recipes"

    mealie_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mealie_updated_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_cached_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    ingredients_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    nutrition_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protein_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    veggie_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nova_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scored_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mealplans: Mapped[list[MealieMealplan]] = relationship(back_populates="recipe")


class MealieMealplan(Base):
    __tablename__ = "mealie_mealplans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    iso_week: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), default="dinner", nullable=False)
    mealie_recipe_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("mealie_recipes.mealie_id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    recipe: Mapped[MealieRecipe | None] = relationship(back_populates="mealplans")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
