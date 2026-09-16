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

//! Python bindings for execution command messages.

use nautilus_core::{UUID4, UnixNanos};
use nautilus_model::{
    enums::OrderSide,
    identifiers::{ClientId, ClientOrderId, InstrumentId, StrategyId, TraderId, VenueOrderId},
    types::{Price, Quantity},
};
use pyo3::prelude::*;

use crate::messages::execution::{BatchCancelOrders, CancelAllOrders, CancelOrder, ModifyOrder};

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl ModifyOrder {
    /// Command to modify an existing order's quantity, price and/or trigger price.
    #[new]
    #[expect(clippy::too_many_arguments)]
    #[pyo3(signature = (
        trader_id,
        strategy_id,
        instrument_id,
        client_order_id,
        command_id,
        ts_init,
        venue_order_id = None,
        quantity = None,
        price = None,
        trigger_price = None,
        client_id = None,
    ))]
    fn py_new(
        trader_id: TraderId,
        strategy_id: StrategyId,
        instrument_id: InstrumentId,
        client_order_id: ClientOrderId,
        command_id: UUID4,
        ts_init: u64,
        venue_order_id: Option<VenueOrderId>,
        quantity: Option<Quantity>,
        price: Option<Price>,
        trigger_price: Option<Price>,
        client_id: Option<ClientId>,
    ) -> Self {
        Self::new(
            trader_id,
            client_id,
            strategy_id,
            instrument_id,
            client_order_id,
            venue_order_id,
            quantity,
            price,
            trigger_price,
            command_id,
            UnixNanos::from(ts_init),
            None,
            None,
        )
    }

    #[getter]
    #[pyo3(name = "trader_id")]
    fn py_trader_id(&self) -> TraderId {
        self.trader_id
    }

    #[getter]
    #[pyo3(name = "client_id")]
    fn py_client_id(&self) -> Option<ClientId> {
        self.client_id
    }

    #[getter]
    #[pyo3(name = "strategy_id")]
    fn py_strategy_id(&self) -> StrategyId {
        self.strategy_id
    }

    #[getter]
    #[pyo3(name = "instrument_id")]
    fn py_instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    #[getter]
    #[pyo3(name = "client_order_id")]
    fn py_client_order_id(&self) -> ClientOrderId {
        self.client_order_id
    }

    #[getter]
    #[pyo3(name = "venue_order_id")]
    fn py_venue_order_id(&self) -> Option<VenueOrderId> {
        self.venue_order_id
    }

    #[getter]
    #[pyo3(name = "quantity")]
    fn py_quantity(&self) -> Option<Quantity> {
        self.quantity
    }

    #[getter]
    #[pyo3(name = "price")]
    fn py_price(&self) -> Option<Price> {
        self.price
    }

    #[getter]
    #[pyo3(name = "trigger_price")]
    fn py_trigger_price(&self) -> Option<Price> {
        self.trigger_price
    }

    #[getter]
    #[pyo3(name = "command_id")]
    fn py_command_id(&self) -> UUID4 {
        self.command_id
    }

    #[getter]
    #[pyo3(name = "ts_init")]
    fn py_ts_init(&self) -> u64 {
        self.ts_init.as_u64()
    }

    fn __repr__(&self) -> String {
        format!("{self}")
    }

    fn __str__(&self) -> String {
        format!("{self}")
    }
}

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl CancelOrder {
    /// Command to cancel an existing order.
    #[new]
    #[expect(clippy::too_many_arguments)]
    #[pyo3(signature = (
        trader_id,
        strategy_id,
        instrument_id,
        client_order_id,
        command_id,
        ts_init,
        venue_order_id = None,
        client_id = None,
    ))]
    fn py_new(
        trader_id: TraderId,
        strategy_id: StrategyId,
        instrument_id: InstrumentId,
        client_order_id: ClientOrderId,
        command_id: UUID4,
        ts_init: u64,
        venue_order_id: Option<VenueOrderId>,
        client_id: Option<ClientId>,
    ) -> Self {
        Self::new(
            trader_id,
            client_id,
            strategy_id,
            instrument_id,
            client_order_id,
            venue_order_id,
            command_id,
            UnixNanos::from(ts_init),
            None,
            None,
        )
    }

    #[getter]
    #[pyo3(name = "trader_id")]
    fn py_trader_id(&self) -> TraderId {
        self.trader_id
    }

    #[getter]
    #[pyo3(name = "client_id")]
    fn py_client_id(&self) -> Option<ClientId> {
        self.client_id
    }

    #[getter]
    #[pyo3(name = "strategy_id")]
    fn py_strategy_id(&self) -> StrategyId {
        self.strategy_id
    }

    #[getter]
    #[pyo3(name = "instrument_id")]
    fn py_instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    #[getter]
    #[pyo3(name = "client_order_id")]
    fn py_client_order_id(&self) -> ClientOrderId {
        self.client_order_id
    }

    #[getter]
    #[pyo3(name = "venue_order_id")]
    fn py_venue_order_id(&self) -> Option<VenueOrderId> {
        self.venue_order_id
    }

    #[getter]
    #[pyo3(name = "command_id")]
    fn py_command_id(&self) -> UUID4 {
        self.command_id
    }

    #[getter]
    #[pyo3(name = "ts_init")]
    fn py_ts_init(&self) -> u64 {
        self.ts_init.as_u64()
    }

    fn __repr__(&self) -> String {
        format!("{self}")
    }

    fn __str__(&self) -> String {
        format!("{self}")
    }
}

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl CancelAllOrders {
    /// Command to cancel all open orders for an instrument, optionally filtered by side.
    #[new]
    #[pyo3(signature = (
        trader_id,
        strategy_id,
        instrument_id,
        order_side,
        command_id,
        ts_init,
        client_id = None,
    ))]
    fn py_new(
        trader_id: TraderId,
        strategy_id: StrategyId,
        instrument_id: InstrumentId,
        order_side: OrderSide,
        command_id: UUID4,
        ts_init: u64,
        client_id: Option<ClientId>,
    ) -> Self {
        Self::new(
            trader_id,
            client_id,
            strategy_id,
            instrument_id,
            order_side,
            command_id,
            UnixNanos::from(ts_init),
            None,
            None,
        )
    }

    #[getter]
    #[pyo3(name = "trader_id")]
    fn py_trader_id(&self) -> TraderId {
        self.trader_id
    }

    #[getter]
    #[pyo3(name = "client_id")]
    fn py_client_id(&self) -> Option<ClientId> {
        self.client_id
    }

    #[getter]
    #[pyo3(name = "strategy_id")]
    fn py_strategy_id(&self) -> StrategyId {
        self.strategy_id
    }

    #[getter]
    #[pyo3(name = "instrument_id")]
    fn py_instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    #[getter]
    #[pyo3(name = "order_side")]
    fn py_order_side(&self) -> OrderSide {
        self.order_side
    }

    #[getter]
    #[pyo3(name = "command_id")]
    fn py_command_id(&self) -> UUID4 {
        self.command_id
    }

    #[getter]
    #[pyo3(name = "ts_init")]
    fn py_ts_init(&self) -> u64 {
        self.ts_init.as_u64()
    }

    fn __repr__(&self) -> String {
        format!("{self}")
    }

    fn __str__(&self) -> String {
        format!("{self}")
    }
}

#[pymethods]
#[pyo3_stub_gen::derive::gen_stub_pymethods]
impl BatchCancelOrders {
    /// Command to cancel a batch of orders for an instrument.
    #[new]
    #[pyo3(signature = (
        trader_id,
        strategy_id,
        instrument_id,
        cancels,
        command_id,
        ts_init,
        client_id = None,
    ))]
    fn py_new(
        trader_id: TraderId,
        strategy_id: StrategyId,
        instrument_id: InstrumentId,
        cancels: Vec<CancelOrder>,
        command_id: UUID4,
        ts_init: u64,
        client_id: Option<ClientId>,
    ) -> Self {
        Self::new(
            trader_id,
            client_id,
            strategy_id,
            instrument_id,
            cancels,
            command_id,
            UnixNanos::from(ts_init),
            None,
            None,
        )
    }

    #[getter]
    #[pyo3(name = "trader_id")]
    fn py_trader_id(&self) -> TraderId {
        self.trader_id
    }

    #[getter]
    #[pyo3(name = "client_id")]
    fn py_client_id(&self) -> Option<ClientId> {
        self.client_id
    }

    #[getter]
    #[pyo3(name = "strategy_id")]
    fn py_strategy_id(&self) -> StrategyId {
        self.strategy_id
    }

    #[getter]
    #[pyo3(name = "instrument_id")]
    fn py_instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    #[getter]
    #[pyo3(name = "cancels")]
    fn py_cancels(&self) -> Vec<CancelOrder> {
        self.cancels.clone()
    }

    #[getter]
    #[pyo3(name = "command_id")]
    fn py_command_id(&self) -> UUID4 {
        self.command_id
    }

    #[getter]
    #[pyo3(name = "ts_init")]
    fn py_ts_init(&self) -> u64 {
        self.ts_init.as_u64()
    }

    fn __repr__(&self) -> String {
        format!("{self}")
    }

    fn __str__(&self) -> String {
        format!("{self}")
    }
}
