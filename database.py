import datetime
import json

import aiosqlite

from config import DB_PATH, DEFAULT_SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    referrer_id INTEGER,
    referral_confirmed INTEGER NOT NULL DEFAULT 0,
    balance REAL NOT NULL DEFAULT 0,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_task_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    link TEXT,
    reward REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(provider, external_task_id)
);

CREATE TABLE IF NOT EXISTS user_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    completed_at TEXT NOT NULL,
    UNIQUE(user_id, task_id)
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    amount REAL NOT NULL,
    recipient_username TEXT,
    payout_method TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_comment TEXT,
    admin_channel_message_id INTEGER,
    public_channel_message_id INTEGER,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    reward REAL NOT NULL,
    max_activations INTEGER NOT NULL,
    activations INTEGER NOT NULL DEFAULT 0,
    required_tasks INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    activated_at TEXT NOT NULL,
    UNIQUE(promo_id, user_id)
);

CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    gift_id TEXT,
    gift_name TEXT,
    price REAL,
    status TEXT,
    admin_id INTEGER,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    external_id TEXT,
    reward REAL NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'task',
    target_type TEXT NOT NULL DEFAULT 'channel',
    click_goal INTEGER NOT NULL DEFAULT 0,
    click_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked_sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(provider, external_id)
);

CREATE TABLE IF NOT EXISTS sponsor_clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sponsor_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, sponsor_id)
);

CREATE TABLE IF NOT EXISTS seen_tasks (
    user_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (user_id, task_key)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    admin_id INTEGER,
    action TEXT,
    data TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS fsm (
    key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS gate_passes (
    user_id INTEGER NOT NULL,
    sponsor_id INTEGER NOT NULL,
    passed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, sponsor_id)
);

CREATE TABLE IF NOT EXISTS daily_prizes (
    day TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    prize REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""

_conn: aiosqlite.Connection | None = None


def now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


async def init_db() -> None:
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.executescript(SCHEMA)
    await _conn.commit()
    await _migrate()
    for key, value in DEFAULT_SETTINGS.items():
        await _conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
    await _conn.commit()


async def _migrate() -> None:
    """Lightweight forward-only migration for columns added after the initial
    CREATE TABLE IF NOT EXISTS was written (that statement does not alter an
    already-existing table)."""
    extra_columns = [
        ("withdrawals", "payout_method", "TEXT"),
        ("withdrawals", "admin_channel_message_id", "INTEGER"),
        ("withdrawals", "public_channel_message_id", "INTEGER"),
        ("promo_codes", "required_tasks", "INTEGER NOT NULL DEFAULT 0"),
        ("sponsors", "kind", "TEXT NOT NULL DEFAULT 'task'"),
        ("sponsors", "target_type", "TEXT NOT NULL DEFAULT 'channel'"),
        ("sponsors", "click_goal", "INTEGER NOT NULL DEFAULT 0"),
        ("sponsors", "click_count", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "referral_confirmed_at", "TEXT"),
        ("fsm", "updated_at", "TEXT"),
    ]
    for table, column, coltype in extra_columns:
        try:
            await _conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        except aiosqlite.OperationalError:
            pass

    # Referrals confirmed before referral_confirmed_at existed: registration
    # time is the best available approximation.
    await _conn.execute(
        "UPDATE users SET referral_confirmed_at = registered_at "
        "WHERE referral_confirmed = 1 AND referral_confirmed_at IS NULL"
    )

    # Gate (mandatory subscription) passes used to be stored as completed
    # tasks, inflating task stats/leaderboards. Move them to gate_passes.
    gate_rows = (
        "SELECT ut.id, ut.user_id, s.id AS sponsor_id, ut.completed_at FROM user_tasks ut "
        "JOIN tasks t ON t.id = ut.task_id "
        "JOIN sponsors s ON t.provider = 'own' AND CAST(t.external_task_id AS INTEGER) = s.id "
        "WHERE s.kind = 'gate'"
    )
    await _conn.execute(
        f"INSERT OR IGNORE INTO gate_passes (user_id, sponsor_id, passed_at) "
        f"SELECT user_id, sponsor_id, completed_at FROM ({gate_rows})"
    )
    await _conn.execute(f"DELETE FROM user_tasks WHERE id IN (SELECT id FROM ({gate_rows}))")
    await _conn.commit()


def conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database is not initialized, call init_db() first")
    return _conn


async def close_db() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


# ---------------------------------------------------------------- settings

async def get_setting(key: str, default: str | None = None) -> str | None:
    cur = await conn().execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else default


async def get_setting_int(key: str, default: int = 0) -> int:
    value = await get_setting(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def get_setting_float(key: str, default: float = 0.0) -> float:
    value = await get_setting(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def get_setting_bool(key: str, default: bool = True) -> bool:
    value = await get_setting(key)
    if value is None:
        return default
    return value == "1"


async def set_setting(key: str, value: str) -> None:
    await conn().execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn().commit()


async def get_photo(key: str) -> str | None:
    value = await get_setting(f"{key}_photo")
    return value or None


async def set_photo(key: str, file_id: str) -> None:
    await set_setting(f"{key}_photo", file_id)


async def delete_photo(key: str) -> None:
    await set_setting(f"{key}_photo", "")


async def get_all_settings() -> dict:
    cur = await conn().execute("SELECT key, value FROM settings ORDER BY key")
    rows = await cur.fetchall()
    return {row["key"]: row["value"] for row in rows}


# ---------------------------------------------------------------- users

async def get_user(telegram_id: int) -> aiosqlite.Row | None:
    cur = await conn().execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    return await cur.fetchone()


async def create_user(
    telegram_id: int, username: str | None, first_name: str | None, referrer_id: int | None
) -> aiosqlite.Row:
    await conn().execute(
        "INSERT INTO users (telegram_id, username, first_name, referrer_id, registered_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (telegram_id, username, first_name, referrer_id, now()),
    )
    await conn().commit()
    return await get_user(telegram_id)


async def update_user_profile(telegram_id: int, username: str | None, first_name: str | None) -> None:
    await conn().execute(
        "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
        (username, first_name, telegram_id),
    )
    await conn().commit()


async def set_user_blocked(telegram_id: int, blocked: bool) -> None:
    await conn().execute(
        "UPDATE users SET is_blocked = ? WHERE telegram_id = ?", (1 if blocked else 0, telegram_id)
    )
    await conn().commit()


async def adjust_balance(telegram_id: int, delta: float) -> None:
    await conn().execute(
        # rounded so fractional rewards (0.1, 0.3, ...) don't drift into
        # 24.999999 that shows as 25 but fails a 25-star withdrawal
        "UPDATE users SET balance = ROUND(balance + ?, 6) WHERE telegram_id = ?", (delta, telegram_id)
    )
    await conn().commit()


async def try_debit(telegram_id: int, amount: float) -> bool:
    """Atomically subtracts amount if the balance covers it. A separate
    read-then-update would let two concurrent requests spend the same stars."""
    cur = await conn().execute(
        "UPDATE users SET balance = MAX(ROUND(balance - ?, 6), 0) "
        "WHERE telegram_id = ? AND ROUND(balance, 6) >= ?",
        (amount, telegram_id, amount),
    )
    await conn().commit()
    return cur.rowcount > 0


async def increment_tasks_completed(telegram_id: int) -> int:
    await conn().execute(
        "UPDATE users SET tasks_completed = tasks_completed + 1 WHERE telegram_id = ?",
        (telegram_id,),
    )
    await conn().commit()
    user = await get_user(telegram_id)
    return user["tasks_completed"]


async def confirm_referral(telegram_id: int) -> bool:
    """Returns True only for the call that actually flipped the flag, so the
    referrer can't be paid twice by concurrent task completions."""
    cur = await conn().execute(
        "UPDATE users SET referral_confirmed = 1, referral_confirmed_at = ? "
        "WHERE telegram_id = ? AND referral_confirmed = 0",
        (now(), telegram_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def count_referrals(telegram_id: int) -> tuple[int, int]:
    cur = await conn().execute(
        "SELECT COUNT(*) AS total, SUM(referral_confirmed) AS confirmed "
        "FROM users WHERE referrer_id = ?",
        (telegram_id,),
    )
    row = await cur.fetchone()
    total = row["total"] or 0
    confirmed = row["confirmed"] or 0
    return total, confirmed


async def list_referrals(telegram_id: int) -> list[aiosqlite.Row]:
    cur = await conn().execute(
        "SELECT * FROM users WHERE referrer_id = ? ORDER BY registered_at DESC",
        (telegram_id,),
    )
    return await cur.fetchall()


def _period_since(period: str) -> str | None:
    now_dt = datetime.datetime.utcnow()
    if period == "day":
        cutoff = now_dt - datetime.timedelta(days=1)
    elif period == "week":
        cutoff = now_dt - datetime.timedelta(days=7)
    elif period == "month":
        cutoff = now_dt - datetime.timedelta(days=30)
    else:
        return None
    return cutoff.isoformat(timespec="seconds")


async def top_inviters_period(period: str, limit: int = 10) -> list[aiosqlite.Row]:
    since = _period_since(period)
    query = (
        "SELECT u1.referrer_id AS user_id, u2.username AS username, COUNT(*) AS cnt "
        "FROM users u1 LEFT JOIN users u2 ON u2.telegram_id = u1.referrer_id "
        # Only confirmed referrals: a bare /start via the link costs nothing,
        # so counting those would let alt accounts farm the daily prize.
        "WHERE u1.referrer_id IS NOT NULL AND u1.referral_confirmed = 1 "
    )
    params: list = []
    if since:
        query += "AND u1.referral_confirmed_at >= ? "
        params.append(since)
    query += "GROUP BY u1.referrer_id ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    cur = await conn().execute(query, params)
    return await cur.fetchall()


async def top_task_completers_period(period: str, limit: int = 10) -> list[aiosqlite.Row]:
    since = _period_since(period)
    query = (
        "SELECT ut.user_id AS user_id, u.username AS username, COUNT(*) AS cnt "
        "FROM user_tasks ut LEFT JOIN users u ON u.telegram_id = ut.user_id "
    )
    params: list = []
    if since:
        query += "WHERE ut.completed_at >= ? "
        params.append(since)
    query += "GROUP BY ut.user_id ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    cur = await conn().execute(query, params)
    return await cur.fetchall()


async def search_user(query: str) -> aiosqlite.Row | None:
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await get_user(int(query))
    cur = await conn().execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (query,)
    )
    return await cur.fetchone()


async def count_users() -> int:
    cur = await conn().execute("SELECT COUNT(*) AS c FROM users")
    row = await cur.fetchone()
    return row["c"]


async def count_active_users(days: int = 7) -> int:
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    cur = await conn().execute(
        "SELECT COUNT(*) AS c FROM users WHERE registered_at >= ?", (since,)
    )
    row = await cur.fetchone()
    return row["c"]


async def sum_balances() -> float:
    cur = await conn().execute("SELECT COALESCE(SUM(balance), 0) AS s FROM users")
    row = await cur.fetchone()
    return row["s"]


async def all_user_ids(only_active: bool = True) -> list[int]:
    query = "SELECT telegram_id FROM users"
    if only_active:
        query += " WHERE is_blocked = 0"
    cur = await conn().execute(query)
    rows = await cur.fetchall()
    return [row["telegram_id"] for row in rows]


# ---------------------------------------------------------------- tasks / user_tasks

async def upsert_task(
    provider: str, external_task_id: str, title: str, description: str, link: str, reward: float
) -> int:
    await conn().execute(
        "INSERT INTO tasks (provider, external_task_id, title, description, link, reward, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(provider, external_task_id) DO UPDATE SET "
        "title = excluded.title, description = excluded.description, link = excluded.link, reward = excluded.reward",
        (provider, external_task_id, title, description, link, reward, now()),
    )
    await conn().commit()
    cur = await conn().execute(
        "SELECT id FROM tasks WHERE provider = ? AND external_task_id = ?",
        (provider, external_task_id),
    )
    row = await cur.fetchone()
    return row["id"]


async def is_task_completed(telegram_id: int, task_db_id: int) -> bool:
    cur = await conn().execute(
        "SELECT 1 FROM user_tasks WHERE user_id = ? AND task_id = ?", (telegram_id, task_db_id)
    )
    return await cur.fetchone() is not None


async def mark_task_completed(telegram_id: int, task_db_id: int) -> bool:
    """Returns True if newly inserted (first-time completion), False if already existed."""
    try:
        await conn().execute(
            "INSERT INTO user_tasks (user_id, task_id, status, completed_at) VALUES (?, ?, 'completed', ?)",
            (telegram_id, task_db_id, now()),
        )
        await conn().commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def completed_task_external_ids(telegram_id: int, provider: str) -> set[str]:
    cur = await conn().execute(
        "SELECT t.external_task_id FROM user_tasks ut "
        "JOIN tasks t ON t.id = ut.task_id "
        "WHERE ut.user_id = ? AND t.provider = ?",
        (telegram_id, provider),
    )
    rows = await cur.fetchall()
    return {row["external_task_id"] for row in rows}


async def count_completed_tasks() -> int:
    cur = await conn().execute("SELECT COUNT(*) AS c FROM user_tasks")
    row = await cur.fetchone()
    return row["c"]


async def user_completed_tasks(telegram_id: int, limit: int = 20) -> list[aiosqlite.Row]:
    cur = await conn().execute(
        "SELECT t.title, t.provider, t.reward, ut.completed_at FROM user_tasks ut "
        "JOIN tasks t ON t.id = ut.task_id WHERE ut.user_id = ? "
        "ORDER BY ut.completed_at DESC LIMIT ?",
        (telegram_id, limit),
    )
    return await cur.fetchall()


# ---------------------------------------------------------------- withdrawals

async def create_withdrawal(
    telegram_id: int,
    username: str | None,
    amount: float,
    recipient_username: str,
    payout_method: str | None = None,
) -> int:
    cur = await conn().execute(
        "INSERT INTO withdrawals (user_id, username, amount, recipient_username, payout_method, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (telegram_id, username, amount, recipient_username, payout_method, now()),
    )
    await conn().commit()
    return cur.lastrowid


async def set_withdrawal_channel_messages(
    withdrawal_id: int, admin_message_id: int | None, public_message_id: int | None
) -> None:
    await conn().execute(
        "UPDATE withdrawals SET admin_channel_message_id = ?, public_channel_message_id = ? WHERE id = ?",
        (admin_message_id, public_message_id, withdrawal_id),
    )
    await conn().commit()


async def get_withdrawal(withdrawal_id: int) -> aiosqlite.Row | None:
    cur = await conn().execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    return await cur.fetchone()


async def finish_withdrawal(withdrawal_id: int, status: str, admin_comment: str | None = None) -> bool:
    """Moves a pending withdrawal to its final status. Returns False if it was
    no longer pending (e.g. two admins pressed the buttons at once)."""
    cur = await conn().execute(
        "UPDATE withdrawals SET status = ?, admin_comment = ?, processed_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (status, admin_comment, now(), withdrawal_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def user_withdrawals(telegram_id: int, limit: int = 20) -> list[aiosqlite.Row]:
    cur = await conn().execute(
        "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (telegram_id, limit),
    )
    return await cur.fetchall()


async def pending_withdrawals(limit: int = 20) -> list[aiosqlite.Row]:
    cur = await conn().execute(
        "SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (limit,),
    )
    return await cur.fetchall()


async def withdrawal_stats() -> tuple[int, float]:
    cur = await conn().execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS s FROM withdrawals WHERE status = 'paid'"
    )
    row = await cur.fetchone()
    return row["c"], row["s"]


# ---------------------------------------------------------------- promo codes

async def create_promo(code: str, reward: float, max_activations: int, required_tasks: int = 0) -> None:
    await conn().execute(
        "INSERT INTO promo_codes (code, reward, max_activations, required_tasks, created_at) VALUES (?, ?, ?, ?, ?)",
        (code, reward, max_activations, required_tasks, now()),
    )
    await conn().commit()


async def get_promo(code: str) -> aiosqlite.Row | None:
    cur = await conn().execute(
        "SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE", (code,)
    )
    return await cur.fetchone()


async def list_promos() -> list[aiosqlite.Row]:
    cur = await conn().execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
    return await cur.fetchall()


async def set_promo_active(promo_id: int, active: bool) -> None:
    await conn().execute(
        "UPDATE promo_codes SET is_active = ? WHERE id = ?", (1 if active else 0, promo_id)
    )
    await conn().commit()


async def delete_promo(promo_id: int) -> None:
    await conn().execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
    await conn().execute("DELETE FROM promo_activations WHERE promo_id = ?", (promo_id,))
    await conn().commit()


async def has_activated_promo(promo_id: int, telegram_id: int) -> bool:
    cur = await conn().execute(
        "SELECT 1 FROM promo_activations WHERE promo_id = ? AND user_id = ?",
        (promo_id, telegram_id),
    )
    return await cur.fetchone() is not None


async def activate_promo(promo_id: int, telegram_id: int) -> str:
    """Returns 'ok', 'already' (this user used it) or 'limit' (no activations
    left / deactivated). Both checks are done by the writes themselves so
    concurrent activations can't exceed the limit or double-credit."""
    try:
        await conn().execute(
            "INSERT INTO promo_activations (promo_id, user_id, activated_at) VALUES (?, ?, ?)",
            (promo_id, telegram_id, now()),
        )
    except aiosqlite.IntegrityError:
        return "already"
    cur = await conn().execute(
        "UPDATE promo_codes SET activations = activations + 1 "
        "WHERE id = ? AND is_active = 1 AND activations < max_activations",
        (promo_id,),
    )
    if cur.rowcount == 0:
        await conn().execute(
            "DELETE FROM promo_activations WHERE promo_id = ? AND user_id = ?", (promo_id, telegram_id)
        )
        await conn().commit()
        return "limit"
    await conn().commit()
    return "ok"


# ---------------------------------------------------------------- gifts

async def log_gift(telegram_id: int, gift_id: str, gift_name: str, price: float, status: str, admin_id: int, error: str | None = None) -> None:
    await conn().execute(
        "INSERT INTO gifts (user_id, gift_id, gift_name, price, status, admin_id, error, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (telegram_id, gift_id, gift_name, price, status, admin_id, error, now()),
    )
    await conn().commit()


# ---------------------------------------------------------------- sponsors

async def add_sponsor(
    name: str,
    url: str,
    external_id: str | None,
    reward: float,
    kind: str = "task",
    target_type: str = "channel",
    click_goal: int = 0,
) -> None:
    await conn().execute(
        "INSERT INTO sponsors (name, url, external_id, reward, kind, target_type, click_goal, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, url, external_id, reward, kind, target_type, click_goal, now()),
    )
    await conn().commit()


async def list_sponsors(active_only: bool = False, kind: str | None = None) -> list[aiosqlite.Row]:
    query = "SELECT * FROM sponsors"
    conditions = []
    params = []
    if active_only:
        conditions.append("is_active = 1")
    if kind:
        conditions.append("kind = ?")
        params.append(kind)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"
    cur = await conn().execute(query, params)
    return await cur.fetchall()


async def get_sponsor(sponsor_id: int) -> aiosqlite.Row | None:
    cur = await conn().execute("SELECT * FROM sponsors WHERE id = ?", (sponsor_id,))
    return await cur.fetchone()


async def set_sponsor_active(sponsor_id: int, active: bool) -> None:
    await conn().execute(
        "UPDATE sponsors SET is_active = ? WHERE id = ?", (1 if active else 0, sponsor_id)
    )
    await conn().commit()


async def delete_sponsor(sponsor_id: int) -> None:
    await conn().execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
    await conn().commit()


async def increment_sponsor_clicks(sponsor_id: int) -> None:
    await conn().execute(
        "UPDATE sponsors SET click_count = click_count + 1 WHERE id = ?", (sponsor_id,)
    )
    sponsor = await get_sponsor(sponsor_id)
    if sponsor and sponsor["click_goal"] and sponsor["click_count"] >= sponsor["click_goal"]:
        await set_sponsor_active(sponsor_id, False)
    await conn().commit()


async def mark_tasks_seen(user_id: int, keys: list[str]) -> None:
    if not keys:
        return
    await conn().executemany(
        "INSERT INTO seen_tasks (user_id, task_key, seen_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, task_key) DO UPDATE SET seen_at = excluded.seen_at",
        [(user_id, k, now()) for k in keys],
    )
    await conn().commit()


async def recently_seen_task_keys(user_id: int, hours: int) -> set[str]:
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).isoformat(timespec="seconds")
    cur = await conn().execute(
        "SELECT task_key FROM seen_tasks WHERE user_id = ? AND seen_at >= ?", (user_id, cutoff)
    )
    return {row[0] for row in await cur.fetchall()}


async def record_gate_pass(user_id: int, sponsor_id: int) -> bool:
    """True if this is the user's first pass of this mandatory sponsor."""
    cur = await conn().execute(
        "INSERT OR IGNORE INTO gate_passes (user_id, sponsor_id, passed_at) VALUES (?, ?, ?)",
        (user_id, sponsor_id, now()),
    )
    await conn().commit()
    return cur.rowcount > 0


async def record_sponsor_click(user_id: int, sponsor_id: int) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO sponsor_clicks (user_id, sponsor_id, created_at) VALUES (?, ?, ?)",
        (user_id, sponsor_id, now()),
    )
    await conn().commit()


async def has_clicked_sponsor(user_id: int, sponsor_id: int) -> bool:
    cur = await conn().execute(
        "SELECT 1 FROM sponsor_clicks WHERE user_id = ? AND sponsor_id = ?", (user_id, sponsor_id)
    )
    return await cur.fetchone() is not None


# ---------------------------------------------------------------- blocked sponsors

async def block_sponsor(provider: str, external_id: str, reason: str | None) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO blocked_sponsors (provider, external_id, reason, created_at) "
        "VALUES (?, ?, ?, ?)",
        (provider, external_id, reason, now()),
    )
    await conn().commit()


async def unblock_sponsor(block_id: int) -> None:
    await conn().execute("DELETE FROM blocked_sponsors WHERE id = ?", (block_id,))
    await conn().commit()


async def list_blocked_sponsors() -> list[aiosqlite.Row]:
    cur = await conn().execute("SELECT * FROM blocked_sponsors ORDER BY created_at DESC")
    return await cur.fetchall()


async def is_sponsor_blocked(provider: str, external_id: str) -> bool:
    cur = await conn().execute(
        "SELECT 1 FROM blocked_sponsors WHERE provider = ? AND external_id = ?",
        (provider, external_id),
    )
    return await cur.fetchone() is not None


# ---------------------------------------------------------------- logs

async def add_log(category: str, action: str, data: dict | None = None, admin_id: int | None = None) -> None:
    await conn().execute(
        "INSERT INTO logs (category, admin_id, action, data, created_at) VALUES (?, ?, ?, ?, ?)",
        (category, admin_id, action, json.dumps(data or {}, ensure_ascii=False), now()),
    )
    await conn().commit()


async def claim_daily_prize(user_id: int, prize: float) -> bool:
    """Reserves today's (UTC) daily invite prize. Only one caller per day gets
    True, even if two admins press the button at the same moment."""
    today = datetime.datetime.utcnow().date().isoformat()
    cur = await conn().execute(
        "INSERT OR IGNORE INTO daily_prizes (day, user_id, prize, created_at) VALUES (?, ?, ?, ?)",
        (today, user_id, prize, now()),
    )
    await conn().commit()
    return cur.rowcount > 0


async def has_log_today(category: str, action: str) -> bool:
    today = datetime.datetime.utcnow().date().isoformat()
    cur = await conn().execute(
        "SELECT 1 FROM logs WHERE category = ? AND action = ? AND created_at >= ? LIMIT 1",
        (category, action, today),
    )
    return await cur.fetchone() is not None


async def fsm_get(key: str) -> tuple[str | None, dict]:
    cur = await conn().execute("SELECT state, data FROM fsm WHERE key = ?", (key,))
    row = await cur.fetchone()
    if not row:
        return None, {}
    try:
        data = json.loads(row["data"]) if row["data"] else {}
    except ValueError:
        data = {}
    return row["state"], data


async def fsm_set_state(key: str, state: str | None) -> None:
    await conn().execute(
        "INSERT INTO fsm (key, state, data, updated_at) VALUES (?, ?, '{}', ?) "
        "ON CONFLICT(key) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
        (key, state, now()),
    )
    await conn().commit()


async def fsm_set_data(key: str, data: dict) -> None:
    await conn().execute(
        "INSERT INTO fsm (key, state, data, updated_at) VALUES (?, NULL, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (key, json.dumps(data, ensure_ascii=False, default=str), now()),
    )
    await conn().commit()


async def fsm_cleanup(days: int = 7) -> None:
    """Drops FSM rows nobody touched for `days` - the task pool is per user,
    so the table would otherwise keep growing with every user ever seen."""
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    await conn().execute("DELETE FROM fsm WHERE updated_at IS NULL OR updated_at < ?", (cutoff,))
    await conn().commit()


async def list_logs(category: str | None = None, limit: int = 20) -> list[aiosqlite.Row]:
    if category and category != "all":
        cur = await conn().execute(
            "SELECT * FROM logs WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        )
    else:
        cur = await conn().execute(
            "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
    return await cur.fetchall()
