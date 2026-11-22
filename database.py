import sqlite3
from pathlib import Path

from constants import CATEGORIES


DB_PATH = Path("data/auction.db")



def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    # Migration: if tables exist but don't have `category` column, migrate and copy data
    # Rewards table
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rewards'"
    )
    if cursor.fetchone():
        cols = [r[1] for r in cursor.execute("PRAGMA table_info(rewards)").fetchall()]
        if "category" not in cols:
            # rename old, create new with category, copy data
            cursor.execute("ALTER TABLE rewards RENAME TO rewards_old")
            cursor.execute(f"""
            CREATE TABLE rewards (
                guild_id TEXT,
                category TEXT DEFAULT '{CATEGORIES[0]}',
                reward_type TEXT,
                stock INTEGER DEFAULT 0,
                limit_per_queue INTEGER DEFAULT 0,
                PRIMARY KEY (
                    guild_id,
                    category,
                    reward_type
                )
            )
            """)
            cursor.execute(
                "INSERT INTO rewards (guild_id, category, reward_type, stock, limit_per_queue) SELECT guild_id, ?, reward_type, stock, limit_per_queue FROM rewards_old",
                (CATEGORIES[0],),
            )
            cursor.execute("DROP TABLE rewards_old")
    else:
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS rewards (
            guild_id TEXT,
            category TEXT DEFAULT '{CATEGORIES[0]}',
            reward_type TEXT,
            stock INTEGER DEFAULT 0,
            limit_per_queue INTEGER DEFAULT 0,
            PRIMARY KEY (
                guild_id,
                category,
                reward_type
            )
        )
        """)

    # Queue plan table
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='queue_plan'"
    )
    if cursor.fetchone():
        cols = [
            r[1] for r in cursor.execute("PRAGMA table_info(queue_plan)").fetchall()
        ]
        if "category" not in cols:
            cursor.execute("ALTER TABLE queue_plan RENAME TO queue_plan_old")
            cursor.execute(f"""
            CREATE TABLE queue_plan (
                guild_id TEXT,
                category TEXT DEFAULT '{CATEGORIES[0]}',
                queue_no INTEGER,
                reward_type TEXT,
                page INTEGER,
                slot INTEGER,
                PRIMARY KEY (
                    guild_id,
                    category,
                    queue_no,
                    reward_type,
                    page,
                    slot
                )
            )
            """)
            cursor.execute(
                "INSERT INTO queue_plan (guild_id, category, queue_no, reward_type, page, slot) SELECT guild_id, ?, queue_no, reward_type, page, slot FROM queue_plan_old",
                (CATEGORIES[0],),
            )
            cursor.execute("DROP TABLE queue_plan_old")
    else:
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS queue_plan (
            guild_id TEXT,
            category TEXT DEFAULT '{CATEGORIES[0]}',
            queue_no INTEGER,
            reward_type TEXT,
            page INTEGER,
            slot INTEGER,
            PRIMARY KEY (
                guild_id,
                category,
                queue_no,
                reward_type,
                page,
                slot
            )
        )
        """)

    # Party plan: which party each Guild League / League Prize queue belongs
    # to, and where the next Card goes. Rows are never touched by the reward
    # or queue tables.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS party_plan (
        guild_id TEXT PRIMARY KEY,
        party_count INTEGER NOT NULL,
        queue_start INTEGER NOT NULL,
        card_start INTEGER NOT NULL,
        day_closed INTEGER NOT NULL DEFAULT 0,
        last_card_party INTEGER,
        used_queue_start INTEGER,
        astro_start INTEGER,
        last_astro_party INTEGER
    )
    """)

    # Migration: older party_plan tables miss the newer columns.
    party_cols = [
        r[1] for r in cursor.execute("PRAGMA table_info(party_plan)").fetchall()
    ]
    for column in ("used_queue_start", "astro_start", "last_astro_party"):
        if column not in party_cols:
            cursor.execute(f"ALTER TABLE party_plan ADD COLUMN {column} INTEGER")

    conn.commit()
    conn.close()


# -------------------------
# Reward functions
# -------------------------


def set_reward_stock(guild_id, reward_type, stock, category=CATEGORIES[0]):
    conn = get_connection()
    conn.execute(
        """
    INSERT INTO rewards
    (
        guild_id,
        category,
        reward_type,
        stock,
        limit_per_queue
    )
    VALUES (?, ?, ?, ?, 0)
    ON CONFLICT(guild_id, category, reward_type)
    DO UPDATE SET stock=excluded.stock
    """,
        (guild_id, category, reward_type, stock),
    )
    conn.commit()
    conn.close()


def set_reward_limit(guild_id, reward_type, limit_per_queue, category=CATEGORIES[0]):
    conn = get_connection()
    conn.execute(
        """
    INSERT INTO rewards
    (
        guild_id,
        category,
        reward_type,
        stock,
        limit_per_queue
    )
    VALUES (?, ?, ?, 0, ?)
    ON CONFLICT(guild_id, category, reward_type)
    DO UPDATE SET limit_per_queue=excluded.limit_per_queue
    """,
        (guild_id, category, reward_type, limit_per_queue),
    )
    conn.commit()
    conn.close()


def get_rewards(guild_id, category=CATEGORIES[0]):
    """
    If category is None, return rewards across all categories for the guild.
    Otherwise return only rewards for that category.
    """
    conn = get_connection()
    cursor = conn.cursor()
    if category is None:
        result = cursor.execute(
            "SELECT * FROM rewards WHERE guild_id= ?", (guild_id,)
        ).fetchall()
    else:
        result = cursor.execute(
            "SELECT * FROM rewards WHERE guild_id= ? AND category= ?",
            (guild_id, category),
        ).fetchall()
    conn.close()
    return result


# -------------------------
# Queue functions
# -------------------------


def clear_queue(guild_id, category=None):
    conn = get_connection()
    if category is None:
        conn.execute("DELETE FROM queue_plan WHERE guild_id= ?", (guild_id,))
    else:
        conn.execute(
            "DELETE FROM queue_plan WHERE guild_id= ? AND category= ?",
            (guild_id, category),
        )
    conn.commit()
    conn.close()


def save_queue_position(
    guild_id, queue_no, reward_type, page, slot, category=CATEGORIES[0]
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO queue_plan (guild_id, category, queue_no, reward_type, page, slot) VALUES (?,?,?,?,?,?)",
        (guild_id, category, queue_no, reward_type, page, slot),
    )
    conn.commit()
    conn.close()


def save_queue_positions_bulk(positions):
    """
    positions: iterable of tuples (guild_id, category, queue_no, reward_type, page, slot)
    Inserts many rows in one transaction for better performance.
    """
    if not positions:
        return
    conn = get_connection()
    conn.executemany(
        "INSERT INTO queue_plan (guild_id, category, queue_no, reward_type, page, slot) VALUES (?,?,?,?,?,?)",
        positions,
    )
    conn.commit()
    conn.close()


def get_queue(guild_id, queue_no, category=None):
    conn = get_connection()
    if category is None:
        result = conn.execute(
            "SELECT * FROM queue_plan WHERE guild_id=? AND queue_no=? ORDER BY category, reward_type, page, slot",
            (guild_id, queue_no),
        ).fetchall()
    else:
        result = conn.execute(
            "SELECT * FROM queue_plan WHERE guild_id=? AND category=? AND queue_no=? ORDER BY reward_type, page, slot",
            (guild_id, category, queue_no),
        ).fetchall()
    conn.close()
    return result


def get_all_queue(guild_id, category=None):
    conn = get_connection()
    if category is None:
        result = conn.execute(
            "SELECT * FROM queue_plan WHERE guild_id=? ORDER BY queue_no, category, reward_type, page, slot",
            (guild_id,),
        ).fetchall()
    else:
        result = conn.execute(
            "SELECT * FROM queue_plan WHERE guild_id=? AND category=? ORDER BY queue_no, reward_type, page, slot",
            (guild_id, category),
        ).fetchall()
    conn.close()
    return result


def get_queue_count(guild_id, category=None):
    conn = get_connection()
    if category is None:
        result = conn.execute(
            "SELECT COALESCE(MAX(queue_no), 0) FROM queue_plan WHERE guild_id=?",
            (guild_id,),
        ).fetchone()
    else:
        result = conn.execute(
            "SELECT COALESCE(MAX(queue_no), 0) FROM queue_plan WHERE guild_id=? AND category=?",
            (guild_id, category),
        ).fetchone()
    conn.close()
    return result[0]


def get_assigned_count(guild_id, category, reward_type):
    conn = get_connection()
    result = conn.execute(
        "SELECT COUNT(*) FROM queue_plan WHERE guild_id=? AND category=? AND reward_type=?",
        (guild_id, category, reward_type),
    ).fetchone()
    conn.close()
    return result[0]


# Backwards-compat thin wrappers (old code expects these names)
def save_reward(guild_id, reward_type, stock, limit_per_queue):
    # Save into default category
    conn = get_connection()
    conn.execute(
        """
    INSERT INTO rewards
    (
        guild_id,
        category,
        reward_type,
        stock,
        limit_per_queue
    )
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(
        guild_id,
        category,
        reward_type
    )
    DO UPDATE SET
        stock=?,
        limit_per_queue=?
    """,
        (
            guild_id,
            CATEGORIES[0],
            reward_type,
            stock,
            limit_per_queue,
            stock,
            limit_per_queue,
        ),
    )
    conn.commit()
    conn.close()


def get_all_rewards(guild_id):
    return get_rewards(guild_id, category=None)

def clear_rewards(guild_id, category=None):
    conn = get_connection()

    if category is None:
        conn.execute(
            "DELETE FROM rewards WHERE guild_id=?",
            (guild_id,),
        )
    else:
        conn.execute(
            "DELETE FROM rewards WHERE guild_id=? AND category=?",
            (guild_id, category),
        )

    conn.commit()
    conn.close()


# -------------------------
# Party plan (Guild League / League Prize)
# -------------------------


def get_party_plan(guild_id):
    """Return the party plan row for a guild, or None if it is not set."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM party_plan WHERE guild_id=?", (guild_id,)
    ).fetchone()
    conn.close()
    return row


def set_party_plan(guild_id, party_count, queue_start, card_start, astro_start):
    conn = get_connection()
    conn.execute(
        """
    INSERT INTO party_plan
    (guild_id, party_count, queue_start, card_start, astro_start, day_closed)
    VALUES (?, ?, ?, ?, ?, 0)
    ON CONFLICT(guild_id)
    DO UPDATE SET
        party_count=excluded.party_count,
        queue_start=excluded.queue_start,
        card_start=excluded.card_start,
        astro_start=excluded.astro_start,
        day_closed=0,
        last_card_party=NULL,
        last_astro_party=NULL,
        used_queue_start=NULL
    """,
        (guild_id, party_count, queue_start, card_start, astro_start),
    )
    conn.commit()
    conn.close()


def update_party_pointers(guild_id, queue_start, card_start, astro_start, day_closed):
    conn = get_connection()
    conn.execute(
        "UPDATE party_plan SET queue_start=?, card_start=?, astro_start=?, day_closed=?, "
        "last_card_party=NULL, last_astro_party=NULL WHERE guild_id=?",
        (queue_start, card_start, astro_start, day_closed, guild_id),
    )
    conn.commit()
    conn.close()


def set_day_closed(guild_id, closed):
    conn = get_connection()
    conn.execute(
        "UPDATE party_plan SET day_closed=? WHERE guild_id=?",
        (1 if closed else 0, guild_id),
    )
    conn.commit()
    conn.close()


def get_max_queue_no(guild_id, categories, reward_type=None):
    """Highest queue number across the given categories (0 if none)."""
    categories = list(categories)
    marks = ",".join("?" for _ in categories)
    sql = (
        "SELECT COALESCE(MAX(queue_no), 0) FROM queue_plan "
        f"WHERE guild_id=? AND category IN ({marks})"
    )
    params = [guild_id, *categories]
    if reward_type is not None:
        sql += " AND reward_type=?"
        params.append(reward_type)
    conn = get_connection()
    result = conn.execute(sql, params).fetchone()
    conn.close()
    return result[0]


def set_last_spread_parties(guild_id, card_party, astro_party):
    """
    Party that got the last "+1" of Card / Astrocore today.
    None means nothing moved, so tomorrow starts where today started.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE party_plan SET last_card_party=?, last_astro_party=? WHERE guild_id=?",
        (card_party, astro_party, guild_id),
    )
    conn.commit()
    conn.close()


def set_used_queue_start(guild_id, queue_start):
    """Remember which party queue 1 had when the queues were generated."""
    conn = get_connection()
    conn.execute(
        "UPDATE party_plan SET used_queue_start=? WHERE guild_id=?",
        (queue_start, guild_id),
    )
    conn.commit()
    conn.close()
