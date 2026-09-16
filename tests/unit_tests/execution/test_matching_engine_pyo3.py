# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

import pytest

from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.nautilus_pyo3 import UUID4
from nautilus_trader.core.nautilus_pyo3 import AccountType
from nautilus_trader.core.nautilus_pyo3 import AggressorSide
from nautilus_trader.core.nautilus_pyo3 import BookType
from nautilus_trader.core.nautilus_pyo3 import CancelAllOrders
from nautilus_trader.core.nautilus_pyo3 import CancelOrder
from nautilus_trader.core.nautilus_pyo3 import ClientOrderId
from nautilus_trader.core.nautilus_pyo3 import ContingencyType
from nautilus_trader.core.nautilus_pyo3 import DefaultFillModel  # type: ignore[attr-defined]
from nautilus_trader.core.nautilus_pyo3 import LimitOrder
from nautilus_trader.core.nautilus_pyo3 import MakerTakerFeeModel  # type: ignore[attr-defined]
from nautilus_trader.core.nautilus_pyo3 import MarketOrder
from nautilus_trader.core.nautilus_pyo3 import ModifyOrder
from nautilus_trader.core.nautilus_pyo3 import OmsType
from nautilus_trader.core.nautilus_pyo3 import OrderAccepted
from nautilus_trader.core.nautilus_pyo3 import OrderCanceled
from nautilus_trader.core.nautilus_pyo3 import OrderExpired
from nautilus_trader.core.nautilus_pyo3 import OrderFilled
from nautilus_trader.core.nautilus_pyo3 import OrderListId
from nautilus_trader.core.nautilus_pyo3 import OrderMatchingEngine
from nautilus_trader.core.nautilus_pyo3 import OrderMatchingEngineConfig
from nautilus_trader.core.nautilus_pyo3 import OrderSide
from nautilus_trader.core.nautilus_pyo3 import OrderSubmitted
from nautilus_trader.core.nautilus_pyo3 import OrderUpdated
from nautilus_trader.core.nautilus_pyo3 import Price
from nautilus_trader.core.nautilus_pyo3 import Quantity
from nautilus_trader.core.nautilus_pyo3 import QuoteTick
from nautilus_trader.core.nautilus_pyo3 import StopMarketOrder
from nautilus_trader.core.nautilus_pyo3 import TimeInForce
from nautilus_trader.core.nautilus_pyo3 import TriggerType
from nautilus_trader.test_kit.rust.identifiers_pyo3 import TestIdProviderPyo3
from nautilus_trader.test_kit.rust.instruments_pyo3 import TestInstrumentProviderPyo3


AUDUSD_SIM = TestInstrumentProviderPyo3.audusd_sim()
ACCOUNT_ID = TestIdProviderPyo3.account_id()
TRADER_ID = TestIdProviderPyo3.trader_id()
STRATEGY_ID = TestIdProviderPyo3.strategy_id()


def make_engine(**config_kwargs) -> OrderMatchingEngine:
    return OrderMatchingEngine(
        instrument=AUDUSD_SIM,
        raw_id=0,
        fill_model=DefaultFillModel(),
        fee_model=MakerTakerFeeModel(),
        book_type=BookType.L1_MBP,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        config=OrderMatchingEngineConfig(**config_kwargs),
        ts_init_ns=0,
    )


def quote(bid: str, ask: str, ts: int = 0) -> QuoteTick:
    return QuoteTick(
        instrument_id=AUDUSD_SIM.id,
        bid_price=Price.from_str(bid),
        ask_price=Price.from_str(ask),
        bid_size=Quantity.from_int(1_000_000),
        ask_size=Quantity.from_int(1_000_000),
        ts_event=ts,
        ts_init=ts,
    )


def submit(order, ts: int = 0):
    order.apply(
        OrderSubmitted(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=order.client_order_id,
            account_id=ACCOUNT_ID,
            event_id=UUID4(),
            ts_event=ts,
            ts_init=ts,
        ),
    )
    return order


def market_order(counter: int = 1, side: OrderSide = OrderSide.BUY, qty: int = 100_000):
    return submit(
        MarketOrder(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=TestIdProviderPyo3.client_order_id(counter),
            order_side=side,
            quantity=Quantity.from_int(qty),
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            quote_quantity=False,
            init_id=UUID4(),
            ts_init=0,
        ),
    )


def limit_order(
    counter: int,
    side: OrderSide,
    price: str,
    qty: int = 100_000,
    time_in_force: TimeInForce = TimeInForce.GTC,
    expire_time: int | None = None,
    contingency_type: ContingencyType | None = None,
    order_list_id: OrderListId | None = None,
    linked_order_ids: list[ClientOrderId] | None = None,
    parent_order_id: ClientOrderId | None = None,
):
    return submit(
        LimitOrder(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=TestIdProviderPyo3.client_order_id(counter),
            order_side=side,
            quantity=Quantity.from_int(qty),
            price=Price.from_str(price),
            time_in_force=time_in_force,
            post_only=False,
            reduce_only=False,
            quote_quantity=False,
            init_id=UUID4(),
            ts_init=0,
            expire_time=expire_time,
            contingency_type=contingency_type,
            order_list_id=order_list_id,
            linked_order_ids=linked_order_ids,
            parent_order_id=parent_order_id,
        ),
    )


def stop_market_order(counter: int, side: OrderSide, trigger_price: str, qty: int = 100_000):
    return submit(
        StopMarketOrder(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=TestIdProviderPyo3.client_order_id(counter),
            order_side=side,
            quantity=Quantity.from_int(qty),
            trigger_price=Price.from_str(trigger_price),
            trigger_type=TriggerType.DEFAULT,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            quote_quantity=False,
            init_id=UUID4(),
            ts_init=0,
        ),
    )


def event_types(events) -> list[type]:
    return [type(e) for e in events]


def test_exposed_at_top_level():
    assert nautilus_pyo3.OrderMatchingEngine is OrderMatchingEngine
    assert nautilus_pyo3.OrderMatchingEngineConfig is OrderMatchingEngineConfig


def test_config_defaults_and_overrides():
    config = OrderMatchingEngineConfig()
    assert config.bar_execution is True
    assert config.reject_stop_orders is True
    assert config.support_gtd_orders is True
    assert config.price_protection_points is None

    config = OrderMatchingEngineConfig(reject_stop_orders=False, price_protection_points=5)
    assert config.reject_stop_orders is False
    assert config.price_protection_points == 5


def test_set_time_and_timestamp():
    engine = make_engine()
    assert engine.timestamp_ns() == 0

    engine.set_time(1_000)
    assert engine.timestamp_ns() == 1_000

    with pytest.raises(ValueError):
        engine.set_time(500)


def test_market_order_fills_against_quote():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))
    assert engine.best_bid_price() == Price.from_str("1.00000")
    assert engine.best_ask_price() == Price.from_str("1.00010")

    order = market_order()
    engine.process_order(order, ACCOUNT_ID)

    events = engine.drain_events()
    assert event_types(events) == [OrderFilled]
    fill = events[0]
    assert fill.client_order_id == order.client_order_id
    assert fill.last_px == Price.from_str("1.00010")
    assert fill.last_qty == Quantity.from_int(100_000)
    assert engine.drain_events() == []


def test_limit_order_rests_then_fills_with_accepted_before_filled():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order = limit_order(1, OrderSide.BUY, "0.99990")
    engine.process_order(order, ACCOUNT_ID)

    events = engine.drain_events()
    assert event_types(events) == [OrderAccepted]
    assert engine.order_exists(order.client_order_id)
    assert [o.client_order_id for o in engine.get_open_orders()] == [order.client_order_id]
    assert len(engine.get_open_bid_orders()) == 1
    assert engine.get_open_ask_orders() == []

    engine.process_quote_tick(quote("0.99980", "0.99990", ts=1))
    engine.iterate(1, AggressorSide.NO_AGGRESSOR)

    events = engine.drain_events()
    assert event_types(events) == [OrderFilled]
    assert events[0].last_px == Price.from_str("0.99990")
    assert not engine.order_exists(order.client_order_id)
    assert engine.get_open_orders() == []


def test_stop_market_order_triggers_and_fills():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order = stop_market_order(1, OrderSide.BUY, "1.00020")
    engine.process_order(order, ACCOUNT_ID)
    assert event_types(engine.drain_events()) == [OrderAccepted]

    engine.process_quote_tick(quote("1.00020", "1.00030", ts=1))
    engine.iterate(1, AggressorSide.NO_AGGRESSOR)

    events = engine.drain_events()
    assert event_types(events) == [OrderFilled]
    assert events[0].last_px == Price.from_str("1.00030")
    assert not engine.order_exists(order.client_order_id)


def test_cancel_order():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order = limit_order(1, OrderSide.BUY, "0.99990")
    engine.process_order(order, ACCOUNT_ID)
    accepted = engine.drain_events()[0]

    engine.process_cancel(
        CancelOrder(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=order.client_order_id,
            command_id=UUID4(),
            ts_init=1,
            venue_order_id=accepted.venue_order_id,
        ),
        ACCOUNT_ID,
    )

    events = engine.drain_events()
    assert event_types(events) == [OrderCanceled]
    assert not engine.order_exists(order.client_order_id)


def test_cancel_all_orders():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    engine.process_order(limit_order(1, OrderSide.BUY, "0.99990"), ACCOUNT_ID)
    engine.process_order(limit_order(2, OrderSide.SELL, "1.00020"), ACCOUNT_ID)
    assert event_types(engine.drain_events()) == [OrderAccepted, OrderAccepted]

    engine.process_cancel_all(
        CancelAllOrders(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            order_side=OrderSide.NO_ORDER_SIDE,
            command_id=UUID4(),
            ts_init=1,
        ),
        ACCOUNT_ID,
    )

    assert event_types(engine.drain_events()) == [OrderCanceled, OrderCanceled]
    assert engine.get_open_orders() == []


def test_modify_order_then_fills_at_new_price():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order = limit_order(1, OrderSide.BUY, "0.99990")
    engine.process_order(order, ACCOUNT_ID)
    accepted = engine.drain_events()[0]

    engine.process_modify(
        ModifyOrder(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=order.client_order_id,
            command_id=UUID4(),
            ts_init=1,
            venue_order_id=accepted.venue_order_id,
            quantity=Quantity.from_int(50_000),
            price=Price.from_str("0.99995"),
        ),
        ACCOUNT_ID,
    )

    events = engine.drain_events()
    assert event_types(events) == [OrderUpdated]
    assert events[0].price == Price.from_str("0.99995")
    assert events[0].quantity == Quantity.from_int(50_000)

    cached = engine.get_order(order.client_order_id)
    assert cached.price == Price.from_str("0.99995")

    engine.process_quote_tick(quote("0.99990", "0.99995", ts=2))
    engine.iterate(2, AggressorSide.NO_AGGRESSOR)

    events = engine.drain_events()
    assert event_types(events) == [OrderFilled]
    assert events[0].last_qty == Quantity.from_int(50_000)


def test_gtd_order_expires_via_set_time_and_iterate():
    engine = make_engine(support_gtd_orders=True)
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    expire_ns = 1_000_000_000
    order = limit_order(
        1,
        OrderSide.BUY,
        "0.99990",
        time_in_force=TimeInForce.GTD,
        expire_time=expire_ns,
    )
    engine.process_order(order, ACCOUNT_ID)
    assert event_types(engine.drain_events()) == [OrderAccepted]

    engine.set_time(expire_ns + 1)
    engine.iterate(expire_ns + 1, AggressorSide.NO_AGGRESSOR)

    events = engine.drain_events()
    assert event_types(events) == [OrderExpired]
    assert not engine.order_exists(order.client_order_id)


def test_oco_contingent_orders_cancel_sibling_on_fill():
    engine = make_engine(support_contingent_orders=True)
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order_list_id = OrderListId("OL-1")
    id1 = TestIdProviderPyo3.client_order_id(1)
    id2 = TestIdProviderPyo3.client_order_id(2)
    order1 = limit_order(
        1,
        OrderSide.BUY,
        "0.99990",
        contingency_type=ContingencyType.OCO,
        order_list_id=order_list_id,
        linked_order_ids=[id2],
    )
    order2 = limit_order(
        2,
        OrderSide.SELL,
        "1.00020",
        contingency_type=ContingencyType.OCO,
        order_list_id=order_list_id,
        linked_order_ids=[id1],
    )

    # Linked orders must be known to the engine's cache before processing
    engine.add_order(order1)
    engine.add_order(order2)
    engine.process_order(order1, ACCOUNT_ID)
    engine.process_order(order2, ACCOUNT_ID)
    assert event_types(engine.drain_events()) == [OrderAccepted, OrderAccepted]

    engine.process_quote_tick(quote("0.99980", "0.99990", ts=1))
    engine.iterate(1, AggressorSide.NO_AGGRESSOR)

    events = engine.drain_events()
    assert event_types(events) == [OrderFilled, OrderCanceled]
    assert events[0].client_order_id == id1
    assert events[1].client_order_id == id2
    assert engine.get_open_orders() == []


def test_reset_clears_state():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))
    engine.process_order(limit_order(1, OrderSide.BUY, "0.99990"), ACCOUNT_ID)

    engine.reset()

    assert engine.drain_events() == []
    assert engine.get_open_orders() == []
    assert engine.best_bid_price() is None
    assert engine.best_ask_price() is None


def test_get_book_and_set_fill_model():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))
    engine.set_fill_model(DefaultFillModel())

    book = engine.get_book()
    assert book.instrument_id == AUDUSD_SIM.id
    assert book.best_bid_price() == Price.from_str("1.00000")


def test_python_defined_fill_model_is_used():
    class NeverFillLimit:
        def is_limit_filled(self) -> bool:
            return False

        def is_slipped(self) -> bool:
            return False

    engine = OrderMatchingEngine(
        instrument=AUDUSD_SIM,
        raw_id=0,
        fill_model=NeverFillLimit(),
        fee_model=MakerTakerFeeModel(),
        book_type=BookType.L1_MBP,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        config=OrderMatchingEngineConfig(),
    )
    engine.process_quote_tick(quote("1.00000", "1.00010"))
    order = limit_order(1, OrderSide.BUY, "0.99990")
    engine.process_order(order, ACCOUNT_ID)
    assert event_types(engine.drain_events()) == [OrderAccepted]

    # Best bid touches the limit price without crossing; the model refuses the fill
    engine.process_quote_tick(quote("0.99990", "0.99995", ts=1))
    engine.iterate(1, AggressorSide.NO_AGGRESSOR)
    assert engine.drain_events() == []
    assert engine.order_exists(order.client_order_id)


def test_resent_order_with_newer_events_replaces_cached_order():
    engine = make_engine()
    engine.process_quote_tick(quote("1.00000", "1.00010"))

    order = limit_order(1, OrderSide.BUY, "0.99990")
    engine.process_order(order, ACCOUNT_ID)
    accepted = engine.drain_events()[0]

    # Simulate the Python side applying the drained event and re-sending the order
    order.apply(accepted)
    order.apply(
        OrderUpdated(
            trader_id=TRADER_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=AUDUSD_SIM.id,
            client_order_id=order.client_order_id,
            quantity=Quantity.from_int(25_000),
            event_id=UUID4(),
            ts_event=1,
            ts_init=1,
            reconciliation=False,
            venue_order_id=accepted.venue_order_id,
            account_id=ACCOUNT_ID,
            price=Price.from_str("0.99990"),
        ),
    )
    engine.add_order(order)

    assert engine.get_order(order.client_order_id).quantity == Quantity.from_int(25_000)
