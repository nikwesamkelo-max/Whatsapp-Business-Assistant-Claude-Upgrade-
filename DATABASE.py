"""
database.py — now with a customer_profiles table: durable, cross-session
memory about each customer (separate from the short-term messages/bookings
history).

This is the same idea as Claude Platform's "memory stores" — persistent
knowledge the agent reads automatically and updates over time — implemented
here with a simple SQLite table since we're on the standard Messages API,
not Managed Agents.
"""

import sqlite3
import json

DB_NAME = "whatsapp.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            user_message TEXT,
            bot_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            preferred_date TEXT,
            preferred_time TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_profiles (
            phone_number TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ---------- Messages (unchanged) ----------

def save_message(phone_number: str, user_message: str, bot_response: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (phone_number, user_message, bot_response)
        VALUES (?, ?, ?)
    """, (phone_number, user_message, bot_response))
    conn.commit()
    conn.close()


def get_all_messages(phone_number: str | None = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if phone_number:
        cursor.execute(
            "SELECT * FROM messages WHERE phone_number = ? ORDER BY id",
            (phone_number,),
        )
    else:
        cursor.execute("SELECT * FROM messages ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_recent_messages(phone_number: str, limit: int = 10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM messages
        WHERE phone_number = ?
        ORDER BY id DESC
        LIMIT ?
    """, (phone_number, limit))
    rows = cursor.fetchall()
    conn.close()
    return list(reversed(rows))


# ---------- Bookings (unchanged) ----------

def create_booking(phone_number: str, preferred_date: str, preferred_time: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bookings (phone_number, preferred_date, preferred_time)
        VALUES (?, ?, ?)
    """, (phone_number, preferred_date, preferred_time))
    conn.commit()
    booking_id = cursor.lastrowid
    conn.close()
    return booking_id


def get_bookings(phone_number: str | None = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if phone_number:
        cursor.execute(
            "SELECT * FROM bookings WHERE phone_number = ? ORDER BY id",
            (phone_number,),
        )
    else:
        cursor.execute("SELECT * FROM bookings ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


# ---------- Customer profile memory (new) ----------

def get_customer_profile(phone_number: str) -> dict:
    """Returns the customer's durable profile, or {} if none exists yet."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT profile_json FROM customer_profiles WHERE phone_number = ?",
        (phone_number,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return json.loads(row[0])


def update_customer_profile(phone_number: str, key: str, value: str) -> dict:
    """Merge one fact into the customer's profile (creates the profile if
    it doesn't exist yet). Returns the full updated profile."""
    profile = get_customer_profile(phone_number)
    profile[key] = value

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO customer_profiles (phone_number, profile_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(phone_number) DO UPDATE SET
            profile_json = excluded.profile_json,
            updated_at = CURRENT_TIMESTAMP
    """, (phone_number, json.dumps(profile)))
    conn.commit()
    conn.close()
    return profile
