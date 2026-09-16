// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! Python bindings for the Rust [`OrderMatchingEngine`].
//!
//! The wrapper owns everything the Rust engine needs that would otherwise be provided by a
//! Rust `SimulatedExchange`: a private [`Cache`], a [`TestClock`] advanced by the caller, and an
//! event handler which buffers every emitted [`OrderEventAny`] until the caller drains it.

use std::{
    cell::{Cell, RefCell},
    fmt::Debug,
    rc::Rc,
};

use nautilus_common::{
    cache::Cache,
    clock::{Clock, TestClock},
    messages::execution::{BatchCancelOrders, CancelAllOrders, CancelOrder, ModifyOrder},
};
use nautilus_core::{UnixNanos, python::to_pyvalue_err};
use nautilus_model::{
    data::{
        Bar, InstrumentClose, OrderBookDelta, OrderBookDeltas, OrderBookDepth10, QuoteTick,
        TradeTick,
    },
    enums::{AccountType, AggressorSide, BookType, MarketStatusAction, OmsType},
    events::{OrderEventAny, OrderFilled},
    identifiers::{AccountId, ClientOrderId, PositionId},
    instruments::{Instrument, InstrumentAny},
    orderbook::OrderBook,
    orders::{Order, OrderAny},
    position::Position,
    python::{
        events::order::order_event_to_pyobject,
        instruments::pyobject_to_instrument_any,
        orders::{order_any_to_pyobject, pyobject_to_order_any},
    },
    types::Price,
};
use pyo3::prelude::*;

use crate::{
    matching_engine::{config::OrderMatchingEngineConfig, engine::OrderMatchingEngine},
    python::{fee::pyobject_to_fee_model_handle, fill::pyobject_to_fill_model_handle},
};

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl OrderMatchingEngineConfig {
    /// Configuration for `OrderMatchingEngine` instances.
    #[new]
    #[expect(clippy::too_many_arguments, clippy::fn_params_excessive_bools)]
    #[pyo3(signature = (
        bar_execution = true,
        bar_adaptive_high_low_ordering = false,
        trade_execution = true,
        liquidity_consumption = false,
        reject_stop_orders = true,
        support_gtd_orders = true,
        support_contingent_orders = true,
        use_position_ids = true,
        use_random_ids = false,
        use_reduce_only = true,
        use_market_order_acks = false,
        queue_position = false,
        oto_full_trigger = false,
        price_protection_points = None,
    ))]
    fn py_new(
        bar_execution: bool,
        bar_adaptive_high_low_ordering: bool,
        trade_execution: bool,
        liquidity_consumption: bool,
        reject_stop_orders: bool,
        support_gtd_orders: bool,
        support_contingent_orders: bool,
        use_position_ids: bool,
        use_random_ids: bool,
        use_reduce_only: bool,
        use_market_order_acks: bool,
        queue_position: bool,
        oto_full_trigger: bool,
        price_protection_points: Option<u32>,
    ) -> Self {
        Self {
            bar_execution,
            bar_adaptive_high_low_ordering,
            trade_execution,
            liquidity_consumption,
            reject_stop_orders,
            support_gtd_orders,
            support_contingent_orders,
            use_position_ids,
            use_random_ids,
            use_reduce_only,
            use_market_order_acks,
            queue_position,
            oto_full_trigger,
            price_protection_points,
        }
    }

    #[getter]
    #[pyo3(name = "bar_execution")]
    const fn py_bar_execution(&self) -> bool {
        self.bar_execution
    }

    #[getter]
    #[pyo3(name = "bar_adaptive_high_low_ordering")]
    const fn py_bar_adaptive_high_low_ordering(&self) -> bool {
        self.bar_adaptive_high_low_ordering
    }

    #[getter]
    #[pyo3(name = "trade_execution")]
    const fn py_trade_execution(&self) -> bool {
        self.trade_execution
    }

    #[getter]
    #[pyo3(name = "liquidity_consumption")]
    const fn py_liquidity_consumption(&self) -> bool {
        self.liquidity_consumption
    }

    #[getter]
    #[pyo3(name = "reject_stop_orders")]
    const fn py_reject_stop_orders(&self) -> bool {
        self.reject_stop_orders
    }

    #[getter]
    #[pyo3(name = "support_gtd_orders")]
    const fn py_support_gtd_orders(&self) -> bool {
        self.support_gtd_orders
    }

    #[getter]
    #[pyo3(name = "support_contingent_orders")]
    const fn py_support_contingent_orders(&self) -> bool {
        self.support_contingent_orders
    }

    #[getter]
    #[pyo3(name = "use_position_ids")]
    const fn py_use_position_ids(&self) -> bool {
        self.use_position_ids
    }

    #[getter]
    #[pyo3(name = "use_random_ids")]
    const fn py_use_random_ids(&self) -> bool {
        self.use_random_ids
    }

    #[getter]
    #[pyo3(name = "use_reduce_only")]
    const fn py_use_reduce_only(&self) -> bool {
        self.use_reduce_only
    }

    #[getter]
    #[pyo3(name = "use_market_order_acks")]
    const fn py_use_market_order_acks(&self) -> bool {
        self.use_market_order_acks
    }

    #[getter]
    #[pyo3(name = "queue_position")]
    const fn py_queue_position(&self) -> bool {
        self.queue_position
    }

    #[getter]
    #[pyo3(name = "oto_full_trigger")]
    const fn py_oto_full_trigger(&self) -> bool {
        self.oto_full_trigger
    }

    #[getter]
    #[pyo3(name = "price_protection_points")]
    const fn py_price_protection_points(&self) -> Option<u32> {
        self.price_protection_points
    }

    fn __repr__(&self) -> String {
        format!("{self:?}")
    }
}

type EventBuffer = Rc<RefCell<Vec<OrderEventAny>>>;

/// State shared between the wrapper and the engine's event handler.
struct HandlerState {
    cache: Rc<RefCell<Cache>>,
    events: EventBuffer,
    oms_type: OmsType,
    position_count: Cell<usize>,
}

impl HandlerState {
    fn handle(&self, event: OrderEventAny) {
        self.apply_event_to_cache(&event);
        if let OrderEventAny::Filled(fill) = &event {
            self.apply_fill_to_positions(fill);
        }
        self.events.borrow_mut().push(event);
    }

    /// Applies `event` to the cached order unless the engine already applied it internally
    /// (some paths call `cache.update_order` before dispatching the same event).
    fn apply_event_to_cache(&self, event: &OrderEventAny) {
        let client_order_id = event.client_order_id();
        let already_applied = self
            .cache
            .borrow()
            .order(&client_order_id)
            .is_some_and(|order| order.event_count() > 0 && order.last_event() == event);

        if already_applied {
            return;
        }

        if let Err(e) = self.cache.borrow_mut().update_order(event) {
            log::debug!("Skipping cache update for {client_order_id}: {e}");
        }
    }

    /// Mirrors the fill into the private cache's positions so the engine's position-aware
    /// logic (reduce-only, hedging position IDs, netting lookups) sees the current exposure.
    fn apply_fill_to_positions(&self, fill: &OrderFilled) {
        let position_id = if self.oms_type == OmsType::Netting {
            PositionId::new(format!("{}-{}", fill.instrument_id, fill.strategy_id))
        } else if let Some(position_id) = self
            .cache
            .borrow()
            .position_id(&fill.client_order_id)
            .copied()
            .or(fill.position_id)
        {
            position_id
        } else {
            let count = self.position_count.get() + 1;
            self.position_count.set(count);
            PositionId::new(format!("P-{}-{count}", fill.instrument_id.venue))
        };

        let existing = {
            let cache = self.cache.borrow();
            cache
                .position(&position_id)
                .map(|position| position.cloned())
        };

        match existing {
            Some(mut position) => {
                if position.trade_ids.contains(&fill.trade_id) {
                    return;
                }
                position.apply(fill);
                if let Err(e) = self.cache.borrow_mut().update_position(&position) {
                    log::debug!("Failed to update mirrored position {position_id}: {e}");
                }
            }
            None => {
                let Some(instrument) = self.cache.borrow().instrument(&fill.instrument_id).cloned()
                else {
                    log::debug!(
                        "No cached instrument {} for position mirror",
                        fill.instrument_id
                    );
                    return;
                };
                let mut fill = fill.clone();
                fill.position_id = Some(position_id);
                let position = Position::new(&instrument, fill);

                if let Err(e) = self
                    .cache
                    .borrow_mut()
                    .add_position(&position, self.oms_type)
                {
                    log::debug!("Failed to add mirrored position {position_id}: {e}");
                }
            }
        }
    }
}

/// Python-facing wrapper around the Rust [`OrderMatchingEngine`].
///
/// Owns a private [`Cache`] and [`TestClock`] and buffers all emitted order events so a
/// Python `SimulatedExchange` can drive matching while remaining the source of truth for
/// order state on the Python side.
#[pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.execution",
    name = "OrderMatchingEngine",
    unsendable
)]
#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.execution")]
pub struct PyOrderMatchingEngine {
    engine: OrderMatchingEngine,
    cache: Rc<RefCell<Cache>>,
    clock: Rc<RefCell<TestClock>>,
    state: Rc<HandlerState>,
    instrument: InstrumentAny,
}

impl Debug for PyOrderMatchingEngine {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct(stringify!(PyOrderMatchingEngine))
            .field("engine", &self.engine)
            .field("instrument", &self.instrument.id())
            .field("pending_events", &self.state.events.borrow().len())
            .finish_non_exhaustive()
    }
}

impl PyOrderMatchingEngine {
    fn cache_order(&self, order: &OrderAny, position_id: Option<PositionId>) {
        let exists = self
            .cache
            .borrow()
            .order(&order.client_order_id())
            .is_some();

        let result = if exists {
            let stale = self
                .cache
                .borrow()
                .order(&order.client_order_id())
                .is_some_and(|cached| cached.event_count() < order.event_count());
            if stale {
                self.cache.borrow_mut().replace_order(order)
            } else {
                Ok(())
            }
        } else {
            self.cache
                .borrow_mut()
                .add_order(order.clone(), position_id, None, false)
        };

        if let Err(e) = result {
            log::debug!("Failed to cache order {}: {e}", order.client_order_id());
        }
    }

    fn cached_order_to_pyobject(
        &self,
        py: Python<'_>,
        client_order_id: ClientOrderId,
    ) -> PyResult<Option<Py<PyAny>>> {
        let order = self
            .cache
            .borrow()
            .order(&client_order_id)
            .map(|o| o.clone());
        order.map(|o| order_any_to_pyobject(py, o)).transpose()
    }

    fn resting_orders_to_pyobjects(
        &self,
        py: Python<'_>,
        client_order_ids: impl IntoIterator<Item = ClientOrderId>,
    ) -> PyResult<Vec<Py<PyAny>>> {
        client_order_ids
            .into_iter()
            .filter_map(|id| self.cached_order_to_pyobject(py, id).transpose())
            .collect()
    }
}

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl PyOrderMatchingEngine {
    /// Creates a new order matching engine for `instrument`.
    ///
    /// `fill_model` and `fee_model` may be built-in `nautilus_pyo3` models or Python objects
    /// implementing the corresponding protocol.
    #[new]
    #[expect(clippy::too_many_arguments)]
    #[pyo3(signature = (
        instrument,
        raw_id,
        fill_model,
        fee_model,
        book_type,
        oms_type,
        account_type,
        config,
        ts_init_ns = 0,
    ))]
    fn py_new(
        py: Python<'_>,
        instrument: Py<PyAny>,
        raw_id: u32,
        fill_model: &Bound<'_, PyAny>,
        fee_model: &Bound<'_, PyAny>,
        book_type: BookType,
        oms_type: OmsType,
        account_type: AccountType,
        config: OrderMatchingEngineConfig,
        ts_init_ns: u64,
    ) -> PyResult<Self> {
        let instrument = pyobject_to_instrument_any(py, instrument)?;
        let fill_model = pyobject_to_fill_model_handle(fill_model)?;
        let fee_model = pyobject_to_fee_model_handle(fee_model)?;

        let mut test_clock = TestClock::new();
        test_clock.advance_time(UnixNanos::from(ts_init_ns), true);
        let clock = Rc::new(RefCell::new(test_clock));
        let dyn_clock: Rc<RefCell<dyn Clock>> = clock.clone();

        let cache = Rc::new(RefCell::new(Cache::default()));
        cache
            .borrow_mut()
            .add_instrument(instrument.clone())
            .map_err(to_pyvalue_err)?;

        let mut engine = OrderMatchingEngine::new(
            instrument.clone(),
            raw_id,
            fill_model,
            fee_model,
            book_type,
            oms_type,
            account_type,
            dyn_clock,
            cache.clone(),
            config,
        );
        let state = Rc::new(HandlerState {
            cache: cache.clone(),
            events: Rc::new(RefCell::new(Vec::new())),
            oms_type,
            position_count: Cell::new(0),
        });
        let handler_state = state.clone();
        engine.set_event_handler(Rc::new(move |event: OrderEventAny| {
            handler_state.handle(event);
        }));

        Ok(Self {
            engine,
            cache,
            clock,
            state,
            instrument,
        })
    }

    fn __repr__(&self) -> String {
        format!(
            "OrderMatchingEngine(instrument_id={}, raw_id={}, book_type={}, oms_type={}, account_type={})",
            self.engine.instrument.id(),
            self.engine.raw_id,
            self.engine.book_type,
            self.engine.oms_type,
            self.engine.account_type,
        )
    }

    /// Sets the engine clock to `ts_ns` (must be non-decreasing).
    #[pyo3(name = "set_time")]
    fn py_set_time(&self, ts_ns: u64) -> PyResult<()> {
        let to = UnixNanos::from(ts_ns);
        let now = self.clock.borrow().timestamp_ns();
        if to < now {
            return Err(to_pyvalue_err(format!(
                "Clock time must be non-decreasing: {to} < {now}"
            )));
        }
        self.clock.borrow_mut().advance_time(to, true);
        Ok(())
    }

    /// Returns the engine clock's current UNIX timestamp in nanoseconds.
    #[pyo3(name = "timestamp_ns")]
    fn py_timestamp_ns(&self) -> u64 {
        self.clock.borrow().timestamp_ns().as_u64()
    }

    #[pyo3(name = "process_order_book_delta")]
    fn py_process_order_book_delta(&mut self, delta: OrderBookDelta) -> PyResult<()> {
        self.engine
            .process_order_book_delta(&delta)
            .map_err(to_pyvalue_err)?;
        Ok(())
    }

    #[pyo3(name = "process_order_book_deltas")]
    fn py_process_order_book_deltas(&mut self, deltas: &OrderBookDeltas) -> PyResult<()> {
        self.engine
            .process_order_book_deltas(deltas)
            .map_err(to_pyvalue_err)?;
        Ok(())
    }

    #[pyo3(name = "process_order_book_depth10")]
    fn py_process_order_book_depth10(&mut self, depth: OrderBookDepth10) -> PyResult<()> {
        self.engine
            .process_order_book_depth10(&depth)
            .map_err(to_pyvalue_err)?;
        Ok(())
    }

    #[pyo3(name = "process_quote_tick")]
    fn py_process_quote_tick(&mut self, quote: QuoteTick) {
        self.engine.process_quote_tick(&quote);
    }

    #[pyo3(name = "process_trade_tick")]
    fn py_process_trade_tick(&mut self, trade: TradeTick) {
        self.engine.process_trade_tick(&trade);
    }

    #[pyo3(name = "process_bar")]
    fn py_process_bar(&mut self, bar: Bar) {
        self.engine.process_bar(&bar);
    }

    #[pyo3(name = "process_status")]
    fn py_process_status(&mut self, action: MarketStatusAction) {
        self.engine.process_status(action);
    }

    #[pyo3(name = "process_instrument_close")]
    fn py_process_instrument_close(&mut self, close: InstrumentClose) {
        self.engine.process_instrument_close(close);
    }

    /// Updates the instrument definition used by this engine (and its private cache).
    #[pyo3(name = "update_instrument")]
    fn py_update_instrument(&mut self, py: Python<'_>, instrument: Py<PyAny>) -> PyResult<()> {
        let instrument = pyobject_to_instrument_any(py, instrument)?;
        self.engine
            .update_instrument(instrument.clone())
            .map_err(to_pyvalue_err)?;
        self.cache
            .borrow_mut()
            .add_instrument(instrument.clone())
            .map_err(to_pyvalue_err)?;
        self.instrument = instrument;
        Ok(())
    }

    /// Adds `order` to the engine's private cache without processing it.
    ///
    /// Use this to pre-register linked contingent orders (OTO/OCO/OUO) before the order which
    /// references them is processed, mirroring how the trader cache holds all submitted orders.
    ///
    /// An optional `position_id` indexes the order against an existing position (HEDGING OMS),
    /// mirroring the trader cache's client order ID to position ID index.
    #[pyo3(name = "add_order", signature = (order, position_id=None))]
    fn py_add_order(
        &self,
        py: Python<'_>,
        order: Py<PyAny>,
        position_id: Option<PositionId>,
    ) -> PyResult<()> {
        let order = pyobject_to_order_any(py, order)?;
        self.cache_order(&order, position_id);
        Ok(())
    }

    /// Processes `order`, caching it first so the engine can look it up.
    ///
    /// If an order with the same client order ID is already cached and the incoming order
    /// carries more events, the cached copy is replaced.
    ///
    /// An optional `position_id` indexes the order against an existing position (HEDGING OMS),
    /// mirroring the trader cache's client order ID to position ID index.
    #[pyo3(name = "process_order", signature = (order, account_id, position_id=None))]
    fn py_process_order(
        &mut self,
        py: Python<'_>,
        order: Py<PyAny>,
        account_id: AccountId,
        position_id: Option<PositionId>,
    ) -> PyResult<()> {
        let mut order = pyobject_to_order_any(py, order)?;
        self.cache_order(&order, position_id);
        self.engine.process_order(&mut order, account_id);
        Ok(())
    }

    #[pyo3(name = "process_modify")]
    fn py_process_modify(&mut self, command: &ModifyOrder, account_id: AccountId) {
        self.engine.process_modify(command, account_id);
    }

    #[pyo3(name = "process_cancel")]
    fn py_process_cancel(&mut self, command: &CancelOrder, account_id: AccountId) {
        self.engine.process_cancel(command, account_id);
    }

    #[pyo3(name = "process_cancel_all")]
    fn py_process_cancel_all(&mut self, command: &CancelAllOrders, account_id: AccountId) {
        self.engine.process_cancel_all(command, account_id);
    }

    #[pyo3(name = "process_batch_cancel")]
    fn py_process_batch_cancel(&mut self, command: &BatchCancelOrders, account_id: AccountId) {
        self.engine.process_batch_cancel(command, account_id);
    }

    /// Iterates the matching core, filling/triggering resting orders and expiring GTD orders.
    #[pyo3(name = "iterate")]
    fn py_iterate(&mut self, ts_ns: u64, aggressor_side: AggressorSide) {
        self.engine.iterate(UnixNanos::from(ts_ns), aggressor_side);
    }

    #[pyo3(name = "set_fill_model")]
    fn py_set_fill_model(&mut self, fill_model: &Bound<'_, PyAny>) -> PyResult<()> {
        let fill_model = pyobject_to_fill_model_handle(fill_model)?;
        self.engine.set_fill_model(fill_model);
        Ok(())
    }

    /// Resets the engine, its private cache, and the buffered events.
    ///
    /// The clock is left at its current time (it must remain non-decreasing).
    #[pyo3(name = "reset")]
    fn py_reset(&mut self) {
        self.engine.reset();
        self.cache.borrow_mut().reset();
        if let Err(e) = self
            .cache
            .borrow_mut()
            .add_instrument(self.instrument.clone())
        {
            log::debug!("Failed to re-add instrument after reset: {e}");
        }
        self.state.events.borrow_mut().clear();
        self.state.position_count.set(0);
    }

    #[pyo3(name = "best_bid_price")]
    fn py_best_bid_price(&self) -> Option<Price> {
        self.engine.best_bid_price()
    }

    #[pyo3(name = "best_ask_price")]
    fn py_best_ask_price(&self) -> Option<Price> {
        self.engine.best_ask_price()
    }

    /// Returns a copy of the internal order book.
    #[pyo3(name = "get_book")]
    fn py_get_book(&self) -> OrderBook {
        self.engine.get_book().clone()
    }

    /// Returns all open orders (as cached by the engine) resting in the matching core.
    #[pyo3(name = "get_open_orders")]
    fn py_get_open_orders(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let ids: Vec<ClientOrderId> = self
            .engine
            .get_open_orders()
            .iter()
            .map(|o| o.client_order_id)
            .collect();
        self.resting_orders_to_pyobjects(py, ids)
    }

    #[pyo3(name = "get_open_bid_orders")]
    fn py_get_open_bid_orders(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let ids: Vec<ClientOrderId> = self
            .engine
            .get_open_bid_orders()
            .iter()
            .map(|o| o.client_order_id)
            .collect();
        self.resting_orders_to_pyobjects(py, ids)
    }

    #[pyo3(name = "get_open_ask_orders")]
    fn py_get_open_ask_orders(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let ids: Vec<ClientOrderId> = self
            .engine
            .get_open_ask_orders()
            .iter()
            .map(|o| o.client_order_id)
            .collect();
        self.resting_orders_to_pyobjects(py, ids)
    }

    #[pyo3(name = "order_exists")]
    fn py_order_exists(&self, client_order_id: ClientOrderId) -> bool {
        self.engine.order_exists(client_order_id)
    }

    /// Returns the cached copy of the order (with all engine events applied), if any.
    #[pyo3(name = "get_order")]
    fn py_get_order(
        &self,
        py: Python<'_>,
        client_order_id: ClientOrderId,
    ) -> PyResult<Option<Py<PyAny>>> {
        self.cached_order_to_pyobject(py, client_order_id)
    }

    /// Returns all buffered order events in emission order and clears the buffer.
    #[pyo3(name = "drain_events")]
    fn py_drain_events(&mut self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let events = std::mem::take(&mut *self.state.events.borrow_mut());
        events
            .into_iter()
            .map(|event| order_event_to_pyobject(py, event))
            .collect()
    }
}
