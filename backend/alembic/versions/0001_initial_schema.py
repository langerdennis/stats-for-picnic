"""Initial schema for Stats for Picnic v1

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "products",
        sa.Column("picnic_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit_quantity", sa.String(length=128), nullable=True),
        sa.Column("parsed_weight_g", sa.Float(), nullable=True),
        sa.Column("picnic_category", sa.String(length=128), nullable=True),
        sa.Column("image_id", sa.String(length=255), nullable=True),
        sa.Column("gtin", sa.String(length=64), nullable=True),
        sa.Column("is_food", sa.Boolean(), nullable=False),
        sa.Column("bucket", sa.String(length=32), nullable=False),
        sa.Column("kcal_per_100g", sa.Float(), nullable=True),
        sa.Column("protein_g_per_100g", sa.Float(), nullable=True),
        sa.Column("carbs_g_per_100g", sa.Float(), nullable=True),
        sa.Column("sugar_g_per_100g", sa.Float(), nullable=True),
        sa.Column("fat_g_per_100g", sa.Float(), nullable=True),
        sa.Column("fiber_g_per_100g", sa.Float(), nullable=True),
        sa.Column("nova_group", sa.Integer(), nullable=True),
        sa.Column("nutriscore_grade", sa.String(length=4), nullable=True),
        sa.Column("enrichment_source", sa.String(length=32), nullable=False),
        sa.Column("enrichment_confidence", sa.Float(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("ignored_reason", sa.String(length=64), nullable=True),
        sa.Column("manual_override", sa.Boolean(), nullable=False),
        sa.Column("purchase_count", sa.Integer(), nullable=False),
        sa.Column("last_purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("picnic_id"),
    )
    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("iso_week", sa.String(length=16), nullable=False),
        sa.Column("total_price_cents", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("protein_per_1000_kcal", sa.Float(), nullable=True),
        sa.Column("fresh_share_pct", sa.Float(), nullable=True),
        sa.Column("nova_1_2_share_pct", sa.Float(), nullable=True),
        sa.Column("snack_share_pct", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("delivery_id"),
    )
    op.create_index("ix_deliveries_iso_week", "deliveries", ["iso_week"], unique=False)
    op.create_table(
        "delivery_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("picnic_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["deliveries.delivery_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["picnic_id"], ["products.picnic_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_items_delivery_id", "delivery_items", ["delivery_id"], unique=False)
    op.create_index("ix_delivery_items_picnic_id", "delivery_items", ["picnic_id"], unique=False)
    op.create_table(
        "cart_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_price_cents", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("next_slot_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("computed_metrics_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "mealie_recipes",
        sa.Column("mealie_id", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mealie_updated_at", sa.String(length=64), nullable=True),
        sa.Column("image_cached_path", sa.String(length=512), nullable=True),
        sa.Column("ingredients_json", sa.Text(), nullable=False),
        sa.Column("nutrition_json", sa.Text(), nullable=False),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("score_summary", sa.String(length=255), nullable=True),
        sa.Column("protein_level", sa.String(length=32), nullable=True),
        sa.Column("veggie_level", sa.String(length=32), nullable=True),
        sa.Column("nova_estimate", sa.Integer(), nullable=True),
        sa.Column("scored_source", sa.String(length=32), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("mealie_id"),
    )
    op.create_table(
        "mealie_mealplans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("iso_week", sa.String(length=16), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("mealie_recipe_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["mealie_recipe_id"], ["mealie_recipes.mealie_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mealie_mealplans_plan_date", "mealie_mealplans", ["plan_date"], unique=False)
    op.create_index("ix_mealie_mealplans_iso_week", "mealie_mealplans", ["iso_week"], unique=False)
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_index("ix_mealie_mealplans_iso_week", table_name="mealie_mealplans")
    op.drop_index("ix_mealie_mealplans_plan_date", table_name="mealie_mealplans")
    op.drop_table("mealie_mealplans")
    op.drop_table("mealie_recipes")
    op.drop_table("cart_snapshots")
    op.drop_index("ix_delivery_items_picnic_id", table_name="delivery_items")
    op.drop_index("ix_delivery_items_delivery_id", table_name="delivery_items")
    op.drop_table("delivery_items")
    op.drop_index("ix_deliveries_iso_week", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_table("products")
    op.drop_table("app_settings")
