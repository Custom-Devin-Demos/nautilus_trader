#!/usr/bin/env python3
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
"""
Backtest matching-engine parity harness.

Runs each offline example under ``examples/backtest/`` twice as a subprocess, once
per matching-engine selection (``NAUTILUS_BACKTEST_MATCHING_ENGINE=<engine>``),
captures the fill sequence, orders/positions reports and final portfolio state of
every ``BacktestEngine`` the example creates, then diffs the two captures.

Usage::

    python scripts/backtest_parity.py                       # cython vs rust
    python scripts/backtest_parity.py --engines cython cython   # determinism baseline
    python scripts/backtest_parity.py --only fx_ema_cross_audusd_ticks --markdown report.md
    make backtest-parity

Exit status is non-zero when any example diverges (or fails to run).

Result capture is performed inside the example's interpreter by ``_child_main``
(this same file is re-executed with ``--capture``): it replaces
``nautilus_trader.backtest.engine.BacktestEngine`` with a subclass that dumps a
JSON snapshot when ``dispose()`` is called (or at interpreter exit as a fallback),
disables ``input()`` prompts, and forces ``random.seed()`` calls without an
explicit seed to use a fixed seed so unseeded ``FillModel`` instances are
deterministic. ``PYTHONHASHSEED=0`` is set for every child.

The ``rust`` selection requires ``BacktestVenueConfig.matching_engine`` to exist;
when it does not the harness fails loudly instead of silently comparing cython
against cython.

"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any


ENGINE_ENV_VAR = "NAUTILUS_BACKTEST_MATCHING_ENGINE"
FIXED_RANDOM_SEED = 0
REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "backtest"
KNOWN_ENGINES = ("cython", "rust")

FILL_FIELDS = (
    "ts_event",
    "instrument_id",
    "client_order_id",
    "order_side",
    "last_qty",
    "last_px",
    "liquidity_side",
    "commission",
)

# Sort keys making report row order independent of dict/hash iteration order
FILL_SORT = ["ts_event", "strategy_id", "instrument_id", "client_order_id"]
ORDER_SORT = ["ts_init", "strategy_id", "instrument_id", "client_order_id"]
POSITION_SORT = ["ts_opened", "ts_closed", "strategy_id", "instrument_id"]
# Report columns holding freshly generated UUIDs (non-deterministic run-to-run)
UUID_COLUMNS = frozenset({"init_id", "event_id"})
# UUID4 fragments embedded in identifiers (e.g. HEDGING position IDs) are masked
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# (regex on the example source, reason) - the first match skips the example
SKIP_RULES: tuple[tuple[str, str], ...] = (
    (r"\bimport databento\b|adapters\.databento", "requires Databento data files"),
    (r"get_cached_binance_http_client", "requires Binance HTTP instrument provider (network)"),
    (r"adapters\.polymarket", "requires Polymarket data loader (network)"),
    (r"adapters\.tardis|Tardis", "requires a Tardis-backed data catalog"),
    (
        r"nautilus_pyo3\.backtest",
        "uses the Rust (v2) BacktestEngine directly, not the Cython SimulatedExchange",
    ),
    (r"catalog_path\s*=|ParquetDataCatalog\(", "requires a local ParquetDataCatalog"),
    (r"expanduser\(\)\s*/\s*\"Data\"|~/Downloads", "requires data under ~/Downloads"),
)

# Literal data-file paths (relative to the repo root) which must exist to run
DATA_FILE_RE = re.compile(r"Path\(\s*\"([^\"]+\.(?:csv|csv\.gz|dbn|dbn\.zst|parquet|json))\"\s*\)")


# ---------------------------------------------------------------------------------------------
# Child process: capture hook
# ---------------------------------------------------------------------------------------------


def _money_to_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _df_records(df: Any, sort_by: list[str] | None = None) -> list[dict[str, Any]]:
    if df is None or len(df) == 0:
        return []
    df = df.reset_index()
    if sort_by:
        keys = [k for k in sort_by if k in df.columns]
        if keys:
            df = df.sort_values(keys, kind="stable")
    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: _jsonable(v) for k, v in row.items() if k not in UUID_COLUMNS})
    return records


def _jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return UUID_RE.sub("<uuid>", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    try:
        if value != value:  # NaN
            return None
    except Exception:  # noqa: S110
        pass
    return UUID_RE.sub("<uuid>", str(value))


def snapshot_engine(engine: Any) -> dict[str, Any]:
    """
    Build a JSON-serialisable snapshot of a (not yet disposed) ``BacktestEngine``.
    """
    trader = engine.trader
    cache = engine.cache
    portfolio = engine.portfolio

    fills_df = trader.generate_fills_report()
    fills = []
    for row in _df_records(fills_df, sort_by=[*FILL_SORT, "trade_id"]):
        fills.append({k: row.get(k) for k in FILL_FIELDS})

    orders = _df_records(trader.generate_orders_report(), sort_by=ORDER_SORT)
    order_fills = _df_records(trader.generate_order_fills_report(), sort_by=ORDER_SORT)
    positions = _df_records(trader.generate_positions_report(), sort_by=POSITION_SORT)

    accounts = {}
    for account in cache.accounts():
        venue = account.id.get_issuer()
        accounts[str(account.id)] = {
            "venue": venue,
            "balances_total": {
                str(cur): _money_to_str(m) for cur, m in account.balances_total().items()
            },
            "balances_free": {
                str(cur): _money_to_str(m) for cur, m in account.balances_free().items()
            },
            "balances_locked": {
                str(cur): _money_to_str(m) for cur, m in account.balances_locked().items()
            },
            "commissions": {str(cur): _money_to_str(m) for cur, m in account.commissions().items()},
        }

    net_positions = {}
    realized = {}
    unrealized = {}
    for instrument in cache.instruments():
        iid = instrument.id
        if not cache.positions(instrument_id=iid):
            continue
        net_positions[str(iid)] = str(portfolio.net_position(iid))
        realized[str(iid)] = _money_to_str(portfolio.realized_pnl(iid))
        unrealized[str(iid)] = _money_to_str(portfolio.unrealized_pnl(iid))

    return {
        "instance_id": str(engine.instance_id),
        "fills": fills,
        "orders": orders,
        "order_fills": order_fills,
        "positions": positions,
        "portfolio": {
            "accounts": dict(sorted(accounts.items())),
            "net_positions": dict(sorted(net_positions.items())),
            "realized_pnl": dict(sorted(realized.items())),
            "unrealized_pnl": dict(sorted(unrealized.items())),
        },
    }


def _pin_randomness() -> None:
    import builtins
    import random

    builtins.input = lambda *_a, **_k: ""

    _orig_seed = random.seed

    def _seed(a=None, *args, **kwargs):
        if a is None:
            a = FIXED_RANDOM_SEED
        return _orig_seed(a, *args, **kwargs)

    random.seed = _seed
    random.seed(FIXED_RANDOM_SEED)
    try:
        import numpy as np

        np.random.seed(FIXED_RANDOM_SEED)  # noqa: NPY002 (legacy global state used by examples)
    except ImportError:  # pragma: no cover
        pass


def _install_capture_hook(out_path: Path, requested_engine: str) -> None:
    import atexit

    import nautilus_trader.backtest.engine as engine_mod

    if requested_engine == "rust":
        _assert_rust_selectable()

    _pin_randomness()

    snapshots: dict[int, dict[str, Any]] = {}
    engines: list[Any] = []
    base_cls = engine_mod.BacktestEngine

    def _flush() -> None:
        payload = {
            "engine": requested_engine,
            "engines": [snapshots[id(e)] for e in engines if id(e) in snapshots],
        }
        out_path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))

    class ParityBacktestEngine(base_cls):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            engines.append(self)

        def _parity_capture(self) -> None:
            if id(self) in snapshots:
                return
            snapshots[id(self)] = snapshot_engine(self)
            _flush()

        def end(self):
            super().end()
            self._parity_capture()

        def dispose(self):
            self._parity_capture()
            super().dispose()

    engine_mod.BacktestEngine = ParityBacktestEngine
    atexit.register(_flush)


def _assert_rust_selectable() -> None:
    from nautilus_trader.backtest.config import BacktestVenueConfig

    if "matching_engine" not in getattr(BacktestVenueConfig, "__struct_fields__", ()):
        sys.stderr.write(
            f"ERROR: {ENGINE_ENV_VAR}=rust requested but BacktestVenueConfig has no "
            "`matching_engine` field, so the Rust matching engine cannot be selected "
            "(this build would silently run the Cython engine).\n",
        )
        sys.exit(3)


def _child_main(script: Path, out_path: Path, requested_engine: str) -> None:
    import runpy

    _install_capture_hook(out_path, requested_engine)
    sys.argv = [str(script)]
    sys.path.insert(0, str(script.parent))
    runpy.run_path(str(script), run_name="__main__")


# ---------------------------------------------------------------------------------------------
# Parent process: run + diff
# ---------------------------------------------------------------------------------------------


@dataclass
class DiffResult:
    identical: bool
    fill_count: tuple[int, int]
    differing_fills: int
    first_divergence: str | None
    balance_deltas: dict[str, str] = field(default_factory=dict)
    other: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.identical:
            return f"identical ({self.fill_count[0]} fills)"
        parts = []
        if self.fill_count[0] != self.fill_count[1]:
            parts.append(f"fill count {self.fill_count[0]} vs {self.fill_count[1]}")
        if self.differing_fills:
            parts.append(f"{self.differing_fills} differing fills")
        if self.first_divergence:
            parts.append(f"first divergence: {self.first_divergence}")
        if self.balance_deltas:
            deltas = ", ".join(f"{k}: {v}" for k, v in self.balance_deltas.items())
            parts.append(f"final balance delta: {deltas}")
        parts.extend(self.other)
        return "; ".join(parts) or "differs"


def _flatten_engines(dump: dict[str, Any]) -> list[dict[str, Any]]:
    return list(dump.get("engines", []))


def _balance_delta(a: str | None, b: str | None) -> str | None:
    if a == b:
        return None
    try:
        from decimal import Decimal

        av = Decimal(str(a).split(" ")[0]) if a else Decimal(0)
        bv = Decimal(str(b).split(" ")[0]) if b else Decimal(0)
        return f"{bv - av:+}"
    except Exception:
        return f"{a} -> {b}"


def diff_dumps(a: dict[str, Any], b: dict[str, Any]) -> DiffResult:
    """
    Diff two capture dumps and summarise how they diverge.
    """
    engines_a = _flatten_engines(a)
    engines_b = _flatten_engines(b)
    other: list[str] = []
    if len(engines_a) != len(engines_b):
        other.append(f"engine count {len(engines_a)} vs {len(engines_b)}")

    fills_a = [f for e in engines_a for f in e.get("fills", [])]
    fills_b = [f for e in engines_b for f in e.get("fills", [])]
    differing, first = _diff_fills(fills_a, fills_b)

    balance_deltas: dict[str, str] = {}
    for ea, eb in zip(engines_a, engines_b, strict=False):
        balance_deltas.update(_diff_balances(ea, eb))
        other.extend(_diff_reports(ea, eb))

    identical = len(engines_a) == len(engines_b) and all(
        _strip_instance(x) == _strip_instance(y) for x, y in zip(engines_a, engines_b, strict=True)
    )
    return DiffResult(
        identical=identical,
        fill_count=(len(fills_a), len(fills_b)),
        differing_fills=differing,
        first_divergence=first,
        balance_deltas=balance_deltas,
        other=other,
    )


def _diff_fills(fills_a: list[dict], fills_b: list[dict]) -> tuple[int, str | None]:
    differing = 0
    first: str | None = None
    for i, (fa, fb) in enumerate(zip(fills_a, fills_b, strict=False)):
        if fa == fb:
            continue
        differing += 1
        if first is None:
            changed = [k for k in FILL_FIELDS if fa.get(k) != fb.get(k)]
            first = (
                f"fill #{i} {fa.get('client_order_id')} @ {fa.get('ts_event')} "
                f"fields {changed}: "
                + ", ".join(f"{fa.get(k)!r} vs {fb.get(k)!r}" for k in changed)
            )
    extra = abs(len(fills_a) - len(fills_b))
    if extra and first is None:
        n = min(len(fills_a), len(fills_b))
        longer, side = (fills_a, "a") if len(fills_a) > len(fills_b) else (fills_b, "b")
        first = f"fill #{n} present only in {side}: {longer[n]}"
    return differing + extra, first


def _diff_balances(ea: dict[str, Any], eb: dict[str, Any]) -> dict[str, str]:
    deltas: dict[str, str] = {}
    acc_a = ea.get("portfolio", {}).get("accounts", {})
    acc_b = eb.get("portfolio", {}).get("accounts", {})
    for acc_id in sorted(set(acc_a) | set(acc_b)):
        bal_a = acc_a.get(acc_id, {}).get("balances_total", {})
        bal_b = acc_b.get(acc_id, {}).get("balances_total", {})
        for cur in sorted(set(bal_a) | set(bal_b)):
            delta = _balance_delta(bal_a.get(cur), bal_b.get(cur))
            if delta is not None:
                deltas[f"{acc_id}/{cur}"] = delta
    return deltas


def _diff_reports(ea: dict[str, Any], eb: dict[str, Any]) -> list[str]:
    pa = ea.get("portfolio", {})
    pb = eb.get("portfolio", {})
    other = [
        f"{key} differ"
        for key in ("net_positions", "realized_pnl", "unrealized_pnl")
        if pa.get(key) != pb.get(key)
    ]
    other += [
        f"{key} report differs"
        for key in ("orders", "order_fills", "positions")
        if ea.get(key) != eb.get(key)
    ]
    return other


def _strip_instance(engine: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in engine.items() if k != "instance_id"}


def skip_reason(script: Path) -> str | None:
    """
    Return why ``script`` cannot run offline, or ``None`` if it can.
    """
    source = script.read_text(errors="replace")
    for pattern, reason in SKIP_RULES:
        if re.search(pattern, source):
            return reason
    for match in DATA_FILE_RE.finditer(source):
        data_file = Path(match.group(1)).expanduser()
        if not (data_file.is_absolute() or (REPO_ROOT / data_file).exists()):
            return f"requires external data file {data_file}"
    return None


def discover_examples(only: list[str] | None) -> tuple[list[Path], dict[Path, str]]:
    scripts = sorted(p for p in EXAMPLES_DIR.glob("*.py") if p.is_file())
    if only:
        wanted = {Path(o).stem for o in only}
        scripts = [s for s in scripts if s.stem in wanted]
        missing = wanted - {s.stem for s in scripts}
        if missing:
            raise SystemExit(f"unknown example(s): {sorted(missing)}")
    skipped = {}
    selected = []
    for s in scripts:
        reason = skip_reason(s)
        if reason and not only:
            skipped[s] = reason
        else:
            selected.append(s)
    return selected, skipped


def run_example(script: Path, engine: str, out_path: Path, timeout: int) -> tuple[int, str]:
    env = dict(os.environ)
    env[ENGINE_ENV_VAR] = engine
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--capture",
        str(script),
        str(out_path),
        engine,
    ]
    # Examples may write side files (e.g. tearsheets) to the CWD; keep them out of the repo
    scratch = out_path.parent / f"{out_path.stem}.cwd"
    scratch.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=scratch,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


@dataclass
class ExampleOutcome:
    name: str
    status: str  # identical | diverged | skipped | error
    detail: str
    fills: str = ""


def markdown_table(outcomes: list[ExampleOutcome], engines: tuple[str, str]) -> str:
    lines = [
        f"| Example | Status | Fills ({engines[0]} / {engines[1]}) | Detail |",
        "|---|---|---|---|",
    ]
    for o in outcomes:
        detail = o.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{o.name}` | {o.status} | {o.fills} | {detail} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="example stems to run (default: all offline examples)",
    )
    parser.add_argument("--engines", nargs=2, default=["cython", "rust"], metavar=("A", "B"))
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / ".parity")
    parser.add_argument("--keep-artifacts", action="store_true", help="keep JSON dumps and logs")
    parser.add_argument("--markdown", type=Path, help="write a markdown summary table to this path")
    parser.add_argument("--timeout", type=int, default=1800, help="per-run timeout in seconds")
    args = parser.parse_args(argv)

    for engine in args.engines:
        if engine not in KNOWN_ENGINES:
            parser.error(f"unknown engine {engine!r}; expected one of {KNOWN_ENGINES}")
    if "rust" in args.engines:
        _assert_rust_selectable()

    engines = (args.engines[0], args.engines[1])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    selected, skipped = discover_examples(args.only)

    outcomes: list[ExampleOutcome] = []
    for script, reason in skipped.items():
        print(f"SKIP  {script.stem}: {reason}")
        outcomes.append(ExampleOutcome(script.stem, "skipped", reason))

    for script in selected:
        outcomes.append(_compare_example(script, engines, args.out_dir, args.timeout))
        if not args.keep_artifacts:
            for p in args.out_dir.glob(f"{script.stem}.*"):
                shutil.rmtree(p) if p.is_dir() else p.unlink()

    if not args.keep_artifacts and args.out_dir.exists() and not any(args.out_dir.iterdir()):
        args.out_dir.rmdir()

    table = markdown_table(outcomes, engines)
    if args.markdown:
        args.markdown.write_text(table)
        print(f"\nMarkdown summary written to {args.markdown}")
    else:
        print("\n" + table)

    counts = {
        s: sum(o.status == s for o in outcomes)
        for s in ("identical", "diverged", "error", "skipped")
    }
    print(
        f"{counts['identical']} identical, {counts['diverged']} diverged, {counts['error']} errors, "
        f"{counts['skipped']} skipped ({engines[0]} vs {engines[1]})",
    )
    return 1 if counts["diverged"] or counts["error"] else 0


def _compare_example(
    script: Path,
    engines: tuple[str, str],
    out_dir: Path,
    timeout: int,
) -> ExampleOutcome:
    name = script.stem
    dumps = []
    for idx, engine in enumerate(engines):
        tag = f"{name}.{idx}-{engine}"
        out_path = out_dir / f"{tag}.json"
        out_path.unlink(missing_ok=True)
        print(f"RUN   {name} [{ENGINE_ENV_VAR}={engine}] ...", flush=True)
        try:
            code, output = run_example(script, engine, out_path, timeout)
        except subprocess.TimeoutExpired:
            code, output = -1, f"timed out after {timeout}s"
        (out_dir / f"{tag}.log").write_text(output)
        if code != 0:
            tail = "\n".join(output.strip().splitlines()[-15:])
            error = f"exit {code} with {engine}:\n{textwrap.indent(tail, '    ')}"
        elif not out_path.exists():
            error = (
                f"no capture produced with {engine} (example never created/ended a BacktestEngine)"
            )
        else:
            dumps.append(json.loads(out_path.read_text()))
            continue
        print(f"ERROR {name}: {error}")
        return ExampleOutcome(name, "error", error.splitlines()[0])

    result = diff_dumps(dumps[0], dumps[1])
    fills = f"{result.fill_count[0]} / {result.fill_count[1]}"
    if result.identical:
        print(f"OK    {name}: {result.summary()}")
        return ExampleOutcome(name, "identical", "", fills)
    print(f"DIFF  {name}: {result.summary()}")
    return ExampleOutcome(name, "diverged", result.summary(), fills)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--capture":
        _child_main(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        sys.exit(main())
