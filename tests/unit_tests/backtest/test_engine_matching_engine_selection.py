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

from decimal import Decimal

import pytest

from nautilus_trader.backtest.config import BacktestVenueConfig
from nautilus_trader.backtest.engine import MATCHING_ENGINE_ENV_VAR
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.backtest.engine import OrderMatchingEngine
from nautilus_trader.backtest.engine import RustOrderMatchingEngine
from nautilus_trader.backtest.engine import SimulatedExchange
from nautilus_trader.backtest.engine import resolve_matching_engine
from nautilus_trader.backtest.models import FillModel
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.backtest.models import MakerTakerFeeModel
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.component import TestClock
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.events import OrderAccepted
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import QuoteTickDataWrangler
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


AUDUSD_SIM = TestInstrumentProvider.default_fx_ccy("AUD/USD")

rust_engine_available = pytest.mark.skipif(
    not hasattr(nautilus_pyo3, "OrderMatchingEngine"),
    reason="nautilus_pyo3.OrderMatchingEngine not available in this build",
)


class TestMatchingEngineSelection:
    def test_resolve_defaults_to_cython(self, monkeypatch):
        monkeypatch.delenv(MATCHING_ENGINE_ENV_VAR, raising=False)

        assert resolve_matching_engine(None) == "cython"

    def test_resolve_honours_env_var(self, monkeypatch):
        monkeypatch.setenv(MATCHING_ENGINE_ENV_VAR, "rust")

        assert resolve_matching_engine(None) == "rust"

    def test_resolve_explicit_value_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv(MATCHING_ENGINE_ENV_VAR, "rust")

        assert resolve_matching_engine("cython") == "cython"
        assert resolve_matching_engine("RUST") == "rust"

    @pytest.mark.parametrize("value", ["bogus", ""])
    def test_resolve_invalid_value_raises(self, value):
        with pytest.raises(ValueError):
            resolve_matching_engine(value)

    def test_venue_config_rejects_invalid_value(self):
        with pytest.raises(Exception):
            BacktestVenueConfig(
                name="SIM",
                oms_type="HEDGING",
                account_type="MARGIN",
                starting_balances=["1_000_000 USD"],
                matching_engine="bogus",
            )

    def test_venue_config_default_is_unset(self):
        config = BacktestVenueConfig(
            name="SIM",
            oms_type="HEDGING",
            account_type="MARGIN",
            starting_balances=["1_000_000 USD"],
        )

        assert config.matching_engine is None

    def test_add_venue_invalid_value_raises(self):
        engine = BacktestEngine(
            config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)),
        )

        try:
            with pytest.raises(ValueError):
                engine.add_venue(
                    venue=Venue("SIM"),
                    oms_type=OmsType.HEDGING,
                    account_type=AccountType.MARGIN,
                    starting_balances=[Money(1_000_000, USD)],
                    matching_engine="bogus",
                )
        finally:
            engine.dispose()

    def test_exchange_cython_uses_cython_engine(self, monkeypatch):
        monkeypatch.delenv(MATCHING_ENGINE_ENV_VAR, raising=False)
        exchange = _build_exchange(matching_engine="cython")

        assert exchange.matching_engine == "cython"
        assert isinstance(exchange.get_matching_engine(AUDUSD_SIM.id), OrderMatchingEngine)

    @rust_engine_available
    def test_exchange_rust_uses_rust_engine(self):
        exchange = _build_exchange(matching_engine="rust")

        assert exchange.matching_engine == "rust"
        assert isinstance(exchange.get_matching_engine(AUDUSD_SIM.id), RustOrderMatchingEngine)


def _build_exchange(matching_engine: str) -> SimulatedExchange:
    clock = TestClock()
    msgbus = MessageBus(trader_id=TestIdStubs.trader_id(), clock=clock)
    cache = TestComponentStubs.cache()
    portfolio = Portfolio(msgbus=msgbus, cache=cache, clock=clock)
    exchange = SimulatedExchange(
        venue=Venue("SIM"),
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(1_000_000, USD)],
        default_leverage=Decimal(50),
        leverages={},
        modules=[],
        fill_model=FillModel(),
        fee_model=MakerTakerFeeModel(),
        portfolio=portfolio,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        latency_model=LatencyModel(0),
        matching_engine=matching_engine,
    )
    exchange.add_instrument(AUDUSD_SIM)

    return exchange


def _build_engine(matching_engine: str | None, tick_count: int = 5_000) -> BacktestEngine:
    config = BacktestEngineConfig(
        logging=LoggingConfig(bypass_logging=True),
        run_analysis=False,
    )
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=Venue("SIM"),
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(1_000_000, USD)],
        matching_engine=matching_engine,
    )
    engine.add_instrument(AUDUSD_SIM)

    provider = TestDataProvider()
    wrangler = QuoteTickDataWrangler(instrument=AUDUSD_SIM)
    ticks = wrangler.process(provider.read_csv_ticks("truefx/audusd-ticks.csv")[:tick_count])
    engine.add_data(ticks)

    return engine


def _run_ema_cross(matching_engine: str) -> tuple[BacktestEngine, EMACross]:
    engine = _build_engine(matching_engine=matching_engine)
    bar_type = BarType.from_str("AUD/USD.SIM-100-TICK-MID-INTERNAL")
    strategy = EMACross(
        config=EMACrossConfig(
            instrument_id=AUDUSD_SIM.id,
            bar_type=bar_type,
            trade_size=Decimal(100_000),
            fast_ema_period=5,
            slow_ema_period=10,
        ),
    )
    engine.add_strategy(strategy)
    engine.run()

    return engine, strategy


def _fill_summary(engine: BacktestEngine) -> list[tuple[str, str, str, str]]:
    fills = []

    for order in engine.cache.orders():
        for event in order.events:
            if isinstance(event, OrderFilled):
                fills.append(
                    (
                        str(order.side),
                        str(event.last_qty),
                        str(event.last_px),
                        str(event.liquidity_side),
                    ),
                )

    return fills


@rust_engine_available
class TestRustMatchingEngineBacktest:
    def test_run_ema_cross_with_rust_engine(self):
        # Arrange, Act
        engine, strategy = _run_ema_cross("rust")

        try:
            # Assert
            orders = engine.cache.orders()
            assert orders

            accepted = [e for o in orders for e in o.events if isinstance(e, OrderAccepted)]
            filled = [e for o in orders for e in o.events if isinstance(e, OrderFilled)]
            assert accepted
            assert filled
            assert engine.cache.positions()
            assert not engine.trader.generate_order_fills_report().empty
            assert not engine.trader.generate_positions_report().empty
        finally:
            engine.dispose()

    def test_cython_and_rust_engines_produce_equivalent_fills(self):
        # Arrange, Act
        cython_engine, _ = _run_ema_cross("cython")
        rust_engine, _ = _run_ema_cross("rust")

        try:
            # Assert
            cython_fills = _fill_summary(cython_engine)
            rust_fills = _fill_summary(rust_engine)
            assert cython_fills
            assert rust_fills == cython_fills

            cython_positions = cython_engine.trader.generate_positions_report()
            rust_positions = rust_engine.trader.generate_positions_report()
            assert len(rust_positions) == len(cython_positions)

            venue = Venue("SIM")
            assert rust_engine.portfolio.account(venue).balance_total(
                USD,
            ) == cython_engine.portfolio.account(venue).balance_total(USD)
        finally:
            cython_engine.dispose()
            rust_engine.dispose()
