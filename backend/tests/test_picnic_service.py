from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from python_picnic_api2 import Picnic2FARequired, PicnicAuthError
from python_picnic_api2.models import (
    Cart,
    Delivery,
    DeliverySummary,
    Order,
    OrderArticle,
    OrderLine,
    Slot,
)
from python_picnic_api2.models.common import Decorator, SelectedSlot

from app.config import get_settings
from app.db import get_session_factory
from app.models import CartSnapshot, Product
from app.models import Delivery as DeliveryModel
from app.services.picnic_service import (
    PicnicReauthRequiredError,
    clear_pending_2fa,
    get_picnic_status,
    has_pending_2fa,
    modify_cart_product,
    request_2fa_code,
    start_login,
    sync_picnic,
    verify_2fa_code,
)
from app.services.settings_store import KEY_PICNIC_AUTH_TOKEN, get_setting, set_setting


class FakePicnic2FAClient:
    def __init__(self, country_code: str = "DE", auth_token: str | None = None):
        self.country_code = country_code
        self.session = SimpleNamespace(auth_token=auth_token)
        self.generated_channels: list[str] = []

    def login(self, username: str, password: str) -> None:
        self.session.auth_token = "pre-2fa-token"
        raise Picnic2FARequired("2FA required")

    def generate_2fa_code(self, channel: str = "SMS") -> None:
        self.generated_channels.append(channel)

    def verify_2fa_code(self, code: str) -> None:
        assert code == "123456"
        self.session.auth_token = "persisted-real-auth-token"


class FakeLivePicnicClient:
    def __init__(self, auth_token: str = "persisted-real-auth-token"):
        self.session = SimpleNamespace(auth_token=auth_token)
        self.added: list[tuple[str, int]] = []

    def get_deliveries(self, summary: bool = True) -> list[DeliverySummary]:
        return [
            DeliverySummary(
                delivery_id="del-live-1",
                status="COMPLETED",
                slot=Slot(window_start="2026-11-24T17:00:00+01:00"),
            )
        ]

    def get_delivery(self, delivery_id: str) -> Delivery:
        return Delivery(
            delivery_id=delivery_id,
            status="COMPLETED",
            slot=Slot(window_start="2026-11-24T17:00:00+01:00"),
            orders=[
                Order(
                    id="ord-1",
                    checkout_total_price=648,
                    items=[
                        OrderLine(
                            id="line-1",
                            price=378,
                            items=[
                                OrderArticle(
                                    id="s_skyr",
                                    name="Arla Skyr Natur",
                                    unit_quantity="500 g",
                                    price=189,
                                    decorators=[Decorator(type="QUANTITY", quantity=2)],
                                )
                            ],
                        ),
                        OrderLine(
                            id="line-2",
                            price=270,
                            items=[
                                OrderArticle(
                                    id="s_brok",
                                    name="Bio Brokkoli",
                                    unit_quantity="500 g",
                                    price=270,
                                    decorators=[Decorator(type="QUANTITY", quantity=1)],
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

    def get_cart(self) -> Cart:
        # Simulate token rotation header update
        self.session.auth_token = "rotated-token-v2"
        return Cart(
            total_count=1,
            checkout_total_price=189,
            selected_slot=SelectedSlot(slot_id="slot-1", state="SELECTED"),
            delivery_slots=[Slot(slot_id="slot-1", window_start="2026-11-28T17:00:00+01:00", selected=True)],
            items=[
                OrderLine(
                    id="cart-line-1",
                    price=189,
                    items=[
                        OrderArticle(
                            id="s_skyr",
                            name="Arla Skyr Natur",
                            unit_quantity="500 g",
                            price=189,
                            decorators=[Decorator(type="QUANTITY", quantity=1)],
                        )
                    ],
                )
            ],
        )

    def add_product(self, product_id: str, count: int = 1) -> Cart:
        self.added.append((product_id, count))
        return Cart(
            total_count=2,
            checkout_total_price=378,
            items=[
                OrderLine(
                    id="cart-line-1",
                    price=378,
                    items=[
                        OrderArticle(
                            id=product_id,
                            name="Arla Skyr Natur",
                            unit_quantity="500 g",
                            price=189,
                            decorators=[Decorator(type="QUANTITY", quantity=2)],
                        )
                    ],
                )
            ],
        )


def test_picnic_2fa_flow_and_token_persistence(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    clear_pending_2fa()

    db = get_session_factory()()
    try:
        step1 = start_login(
            db,
            country_code="DE",
            username="dennis@example.com",
            password="secret",
            api_factory=FakePicnic2FAClient,
        )
        assert step1["status"] == "2fa_required"
        assert has_pending_2fa() is True
        assert get_picnic_status(db) == "2fa_pending"

        gen = request_2fa_code(db, channel="SMS")
        assert gen["status"] == "code_sent"

        step2 = verify_2fa_code(db, code="123456")
        assert step2["status"] == "ok"
        assert has_pending_2fa() is False
        assert get_picnic_status(db) == "ok"
        assert get_setting(db, KEY_PICNIC_AUTH_TOKEN) == "persisted-real-auth-token"
    finally:
        db.close()


def test_picnic_live_sync_and_1click_readd(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    db = get_session_factory()()
    try:
        set_setting(db, KEY_PICNIC_AUTH_TOKEN, "persisted-real-auth-token")
        fake_api = FakeLivePicnicClient()

        res = sync_picnic(db, api=fake_api)  # type: ignore[arg-type]
        assert res["status"] == "ok"
        assert res["synced_deliveries"] == 1
        assert res["cart_item_count"] == 1

        # Token rotation persisted automatically
        assert get_setting(db, KEY_PICNIC_AUTH_TOKEN) == "rotated-token-v2"

        delivery = db.get(DeliveryModel, "del-live-1")
        assert delivery is not None
        assert delivery.item_count == 3
        assert delivery.total_price_cents == 648

        skyr = db.get(Product, "s_skyr")
        assert skyr is not None
        assert skyr.purchase_count == 2

        snap = modify_cart_product(db, product_id="s_skyr", count=1, action="add", api=fake_api)  # type: ignore[arg-type]
        assert fake_api.added == [("s_skyr", 1)]
        assert isinstance(snap, CartSnapshot)
        assert snap.item_count == 2
    finally:
        db.close()


def test_picnic_auth_expiry_marks_reauth_required(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    class ExpiredClient:
        session = SimpleNamespace(auth_token="expired")

        def get_deliveries(self, summary: bool = True):
            raise PicnicAuthError("401 Unauthorized")

    db = get_session_factory()()
    try:
        with pytest.raises(PicnicReauthRequiredError):
            sync_picnic(db, api=ExpiredClient())  # type: ignore[arg-type]
        assert get_picnic_status(db) == "reauth_required"
    finally:
        db.close()


def test_open_delivery_resync_idempotent_purchase_count_and_snapshot_pruning(
    temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()

    class OpenDeliveryClient(FakeLivePicnicClient):
        def get_deliveries(self, summary: bool = True) -> list[DeliverySummary]:
            return [
                DeliverySummary(
                    delivery_id="del-open-1",
                    status="CURRENT",
                    slot=Slot(window_start="2026-11-28T17:00:00+01:00"),
                )
            ]

        def get_delivery(self, delivery_id: str) -> Delivery:
            d = super().get_delivery(delivery_id)
            d.status = "CURRENT"
            return d

    db = get_session_factory()()
    try:
        set_setting(db, KEY_PICNIC_AUTH_TOKEN, "tok")
        fake_api = OpenDeliveryClient()

        # Sync the same still-open delivery 3 times -> purchase_count must stay 2, not 6!
        for _ in range(3):
            sync_picnic(db, api=fake_api)  # type: ignore[arg-type]

        skyr = db.get(Product, "s_skyr")
        assert skyr is not None
        assert skyr.purchase_count == 2

        # Trigger 12 more cart updates -> cart_snapshots must stay pruned to <= 10 rows
        for _ in range(12):
            modify_cart_product(db, product_id="s_skyr", count=1, action="add", api=fake_api)  # type: ignore[arg-type]

        snap_count = db.query(CartSnapshot).count()
        assert snap_count <= 10
    finally:
        db.close()

