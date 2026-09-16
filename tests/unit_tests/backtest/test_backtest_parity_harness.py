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

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "backtest_parity.py"


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("backtest_parity", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fill(ts: int, cid: str, px: str, qty: str = "1.000000") -> dict:
    return {
        "ts_event": f"2020-01-01T00:00:{ts:02d}+00:00",
        "instrument_id": "AUD/USD.SIM",
        "client_order_id": cid,
        "order_side": "BUY",
        "last_qty": qty,
        "last_px": px,
        "liquidity_side": "TAKER",
        "commission": "0.02 USD",
    }


def _dump(engine: str, fills: list[dict], usd_total: str = "1000000.00 USD") -> dict:
    return {
        "engine": engine,
        "engines": [
            {
                "instance_id": f"{engine}-instance",
                "fills": fills,
                "orders": [{"client_order_id": f["client_order_id"]} for f in fills],
                "order_fills": [],
                "positions": [],
                "portfolio": {
                    "accounts": {
                        "SIM-001": {
                            "venue": "SIM",
                            "balances_total": {"USD": usd_total},
                            "balances_free": {"USD": usd_total},
                            "balances_locked": {},
                            "commissions": {},
                        },
                    },
                    "net_positions": {"AUD/USD.SIM": "0"},
                    "realized_pnl": {"AUD/USD.SIM": "0.00 USD"},
                    "unrealized_pnl": {"AUD/USD.SIM": "0.00 USD"},
                },
            },
        ],
    }


def test_diff_identical_ignores_instance_id(harness):
    fills = [_fill(1, "O-1", "0.70001"), _fill(2, "O-2", "0.70002")]
    result = harness.diff_dumps(_dump("cython", fills), _dump("rust", copy.deepcopy(fills)))

    assert result.identical
    assert result.fill_count == (2, 2)
    assert result.differing_fills == 0
    assert result.first_divergence is None
    assert "identical (2 fills)" in result.summary()


def test_diff_reports_first_divergence_and_balance_delta(harness):
    fills_a = [_fill(1, "O-1", "0.70001"), _fill(2, "O-2", "0.70002")]
    fills_b = [_fill(1, "O-1", "0.70001"), _fill(2, "O-2", "0.70003")]

    result = harness.diff_dumps(
        _dump("cython", fills_a, "1000000.00 USD"),
        _dump("rust", fills_b, "999999.50 USD"),
    )

    assert not result.identical
    assert result.differing_fills == 1
    assert result.first_divergence.startswith("fill #1 O-2")
    assert "last_px" in result.first_divergence
    assert result.balance_deltas == {"SIM-001/USD": "-0.50"}
    assert "final balance delta" in result.summary()


def test_diff_counts_missing_fills(harness):
    fills_a = [_fill(1, "O-1", "0.70001"), _fill(2, "O-2", "0.70002")]
    fills_b = fills_a[:1]

    result = harness.diff_dumps(_dump("cython", fills_a), _dump("rust", fills_b))

    assert not result.identical
    assert result.fill_count == (2, 1)
    assert result.differing_fills == 1
    assert "present only in a" in result.first_divergence


def test_skip_rules_detect_external_data(harness):
    examples = harness.EXAMPLES_DIR
    assert harness.skip_reason(examples / "databento_cme_quoter.py") is not None
    assert harness.skip_reason(examples / "crypto_ema_cross_with_binance_provider.py") is not None
    assert harness.skip_reason(examples / "fx_ema_cross_audusd_ticks.py") is None


def test_markdown_table_escapes_pipes(harness):
    outcomes = [
        harness.ExampleOutcome("ex_a", "identical", "", "3 / 3"),
        harness.ExampleOutcome("ex_b", "diverged", "a | b", "3 / 2"),
    ]
    table = harness.markdown_table(outcomes, ("cython", "rust"))

    assert "| `ex_a` | identical | 3 / 3 |  |" in table
    assert "a \\| b" in table
