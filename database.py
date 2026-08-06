import sqlite3
from pathlib import Path


DB_PATH = Path("data/auction.db")


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    conn = get_connection()
    cursor = conn.cursor()


    # Reward config ต่อ Server
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rewards (

        guild_id TEXT,
        reward_type TEXT,

        stock INTEGER DEFAULT 0,
        limit_per_queue INTEGER DEFAULT 0,

        PRIMARY KEY(
            guild_id,
            reward_type
        )

    )
    """)


    # Queue result
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue_plan (

        guild_id TEXT,
        queue_no INTEGER,

        reward_type TEXT,

        page INTEGER,
        slot INTEGER,

        PRIMARY KEY(
            guild_id,
            queue_no,
            reward_type,
            page,
            slot
        )

    )
    """)


    conn.commit()
    conn.close()



# -------------------------
# Reward
# -------------------------

def save_reward(
    guild_id,
    reward_type,
    stock,
    limit_per_queue
):

    conn = get_connection()
    cursor = conn.cursor()


    cursor.execute("""
    INSERT INTO rewards
    (
        guild_id,
        reward_type,
        stock,
        limit_per_queue
    )

    VALUES (?,?,?,?)

    ON CONFLICT(
        guild_id,
        reward_type
    )

    DO UPDATE SET

        stock=?,

        limit_per_queue=?

    """,
    (
        guild_id,
        reward_type,
        stock,
        limit_per_queue,

        stock,
        limit_per_queue
    ))


    conn.commit()
    conn.close()


def set_reward_stock(guild_id, reward_type, stock):
    conn = get_connection()
    conn.execute("""
    INSERT INTO rewards
    (
        guild_id,
        reward_type,
        stock,
        limit_per_queue
    )
    VALUES (?, ?, ?, 0)
    ON CONFLICT(guild_id, reward_type)
    DO UPDATE SET stock=excluded.stock
    """, (
        guild_id,
        reward_type,
        stock
    ))
    conn.commit()
    conn.close()


def set_reward_limit(guild_id, reward_type, limit_per_queue):
    conn = get_connection()
    conn.execute("""
    INSERT INTO rewards
    (
        guild_id,
        reward_type,
        stock,
        limit_per_queue
    )
    VALUES (?, ?, 0, ?)
    ON CONFLICT(guild_id, reward_type)
    DO UPDATE SET limit_per_queue=excluded.limit_per_queue
    """, (
        guild_id,
        reward_type,
        limit_per_queue
    ))
    conn.commit()
    conn.close()


def get_rewards(guild_id):

    conn = get_connection()

    cursor = conn.cursor()


    result = cursor.execute("""
        SELECT *
        FROM rewards

        WHERE guild_id=?

    """,
    (
        guild_id,
    )).fetchall()


    conn.close()

    return result



# -------------------------
# Queue
# -------------------------

def clear_queue(guild_id):

    conn = get_connection()

    conn.execute("""
        DELETE FROM queue_plan
        WHERE guild_id=?
    """,
    (
        guild_id,
    ))

    conn.commit()
    conn.close()



def save_queue_position(
    guild_id,
    queue_no,
    reward_type,
    page,
    slot
):

    conn = get_connection()

    conn.execute("""
    INSERT INTO queue_plan

    VALUES (?,?,?,?,?)

    """,
    (
        guild_id,
        queue_no,
        reward_type,
        page,
        slot
    ))

    conn.commit()
    conn.close()



def get_queue(
    guild_id,
    queue_no
):

    conn = get_connection()

    result = conn.execute("""
    SELECT *

    FROM queue_plan

    WHERE guild_id=?

    AND queue_no=?

    ORDER BY reward_type,page,slot

    """,
    (
        guild_id,
        queue_no
    )).fetchall()


    conn.close()

    return result


def get_all_queue(guild_id):
    conn = get_connection()

    result = conn.execute("""
    SELECT *
    FROM queue_plan
    WHERE guild_id=?
    ORDER BY queue_no, reward_type, page, slot
    """, (
        guild_id,
    )).fetchall()

    conn.close()

    return result


def get_queue_count(guild_id):
    conn = get_connection()

    result = conn.execute("""
        SELECT COALESCE(MAX(queue_no), 0)
        FROM queue_plan
        WHERE guild_id=?
    """, (
        guild_id,
    )).fetchone()

    conn.close()

    return result[0]