import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from config import settings

_DB_PATH: str = settings.DATABASE_PATH


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> Dict[str, Any]:
    """Return rows as dicts instead of tuples."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def init_db() -> None:
    """Create tables and indexes if they do not exist."""
    db_path = Path(_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS bots (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                type       TEXT NOT NULL,
                config     TEXT NOT NULL DEFAULT '{}',
                status     TEXT NOT NULL DEFAULT 'stopped',
                paper      INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                started_at TEXT,
                stopped_at TEXT
            );

            CREATE TABLE IF NOT EXISTS trades (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id    TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                symbol    TEXT NOT NULL,
                side      TEXT NOT NULL,
                price     REAL NOT NULL,
                amount    REAL NOT NULL,
                fee       REAL NOT NULL DEFAULT 0.0,
                profit    REAL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trades_bot_id
                ON trades(bot_id);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol);

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                total_value REAL NOT NULL,
                pnl         REAL NOT NULL DEFAULT 0.0,
                timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON portfolio_snapshots(timestamp);

            CREATE TABLE IF NOT EXISTS backtest_results (
                id         TEXT PRIMARY KEY,
                strategy   TEXT NOT NULL,
                symbol     TEXT NOT NULL,
                params     TEXT NOT NULL DEFAULT '{}',
                days       INTEGER NOT NULL,
                result     TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alert_config (
                id     INTEGER PRIMARY KEY CHECK (id = 1),
                config TEXT NOT NULL DEFAULT '{}'
            );

            -- Ensure a single alert_config row exists.
            INSERT OR IGNORE INTO alert_config (id, config) VALUES (1, '{}');
            """
        )


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield an SQLite connection with dict rows and WAL mode."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def insert_bot(
    bot_id: str,
    name: str,
    bot_type: str,
    config: dict,
    paper: bool,
) -> Dict[str, Any]:
    with get_db() as db:
        db.execute(
            "INSERT INTO bots (id, name, type, config, paper) VALUES (?, ?, ?, ?, ?)",
            (bot_id, name, bot_type, json.dumps(config), int(paper)),
        )
        row = db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
    return row


def get_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as db:
        return db.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()


def list_bots() -> List[Dict[str, Any]]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM bots ORDER BY created_at DESC"
        ).fetchall()


def update_bot_status(
    bot_id: str, status: str, timestamp_col: Optional[str] = None
) -> None:
    with get_db() as db:
        if timestamp_col in ("started_at", "stopped_at"):
            db.execute(
                f"UPDATE bots SET status = ?, {timestamp_col} = datetime('now') WHERE id = ?",
                (status, bot_id),
            )
        else:
            db.execute(
                "UPDATE bots SET status = ? WHERE id = ?", (status, bot_id)
            )


def delete_bot(bot_id: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM bots WHERE id = ?", (bot_id,))


def insert_trade(
    bot_id: str,
    symbol: str,
    side: str,
    price: float,
    amount: float,
    fee: float = 0.0,
    profit: Optional[float] = None,
) -> int:
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO trades (bot_id, symbol, side, price, amount, fee, profit)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (bot_id, symbol, side, price, amount, fee, profit),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_trades(
    bot_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    with get_db() as db:
        if bot_id:
            return db.execute(
                "SELECT * FROM trades WHERE bot_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (bot_id, limit, offset),
            ).fetchall()
        return db.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def get_bot_pnl(bot_id: str) -> Dict[str, float]:
    """Return total PnL and total value for a single bot."""
    with get_db() as db:
        row = db.execute(
            "SELECT COALESCE(SUM(profit), 0.0) AS pnl FROM trades WHERE bot_id = ?",
            (bot_id,),
        ).fetchone()
    return {"pnl": row["pnl"] if row else 0.0, "total_value": 0.0}


def insert_portfolio_snapshot(total_value: float, pnl: float) -> None:
    with get_db() as db:
        db.execute(
            "INSERT INTO portfolio_snapshots (total_value, pnl) VALUES (?, ?)",
            (total_value, pnl),
        )


def get_portfolio_snapshots(limit: int = 500) -> List[Dict[str, Any]]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def insert_backtest_result(
    result_id: str,
    strategy: str,
    symbol: str,
    params: dict,
    days: int,
    result: dict,
) -> None:
    with get_db() as db:
        db.execute(
            """INSERT INTO backtest_results (id, strategy, symbol, params, days, result)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (result_id, strategy, symbol, json.dumps(params), days, json.dumps(result)),
        )


def get_backtest_result(result_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM backtest_results WHERE id = ?", (result_id,)
        ).fetchone()


def list_backtest_results(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def get_alert_config() -> Dict[str, Any]:
    with get_db() as db:
        row = db.execute(
            "SELECT config FROM alert_config WHERE id = 1"
        ).fetchone()
    return json.loads(row["config"]) if row else {}


def update_alert_config(config: dict) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE alert_config SET config = ? WHERE id = 1",
            (json.dumps(config),),
        )


def get_portfolio_summary() -> Dict[str, Any]:
    """Aggregate portfolio stats across all bots."""
    with get_db() as db:
        pnl_row = db.execute(
            "SELECT COALESCE(SUM(profit), 0.0) AS total_pnl FROM trades"
        ).fetchone()
        bot_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM bots"
        ).fetchone()
        trade_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM trades"
        ).fetchone()
        snapshot = db.execute(
            "SELECT total_value FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()

    total_pnl = pnl_row["total_pnl"] if pnl_row else 0.0
    total_value = snapshot["total_value"] if snapshot else 0.0
    num_bots = bot_count["cnt"] if bot_count else 0
    num_trades = trade_count["cnt"] if trade_count else 0

    return {
        "total_value": total_value,
        "total_pnl": total_pnl,
        "pnl_pct": (total_pnl / total_value * 100) if total_value else 0.0,
        "num_bots": num_bots,
        "num_trades": num_trades,
    }
