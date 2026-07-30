
"""
database.py — adds a `customer_profiles` table for persistent customer
memory (preferences, notes) that survives across separate conversations,
on top of the existing per-message chat history and bookings.
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
            name TEXT,
            notes TEXT,
            preferences TEXT,   -- stored as JSON text, e.g. {"event_type": "wedding"}
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
        cursor.execute("SELECT * FROM messages WHERE phone_number = ? ORDER BY id", (phone_number,))
    else:
        cursor.execute("SELECT * FROM messages ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_recent_messages(phone_number: str, limit: int = 10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM messages WHERE phone_number = ?
        ORDER BY id DESC LIMIT ?
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
        cursor.execute("SELECT * FROM bookings WHERE phone_number = ? ORDER BY id", (phone_number,))
    else:
        cursor.execute("SELECT * FROM bookings ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


# ---------- Customer profiles (NEW — persistent memory) ----------

def get_customer_profile(phone_number: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customer_profiles WHERE phone_number = ?", (phone_number,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    _, name, notes, preferences_json, updated_at = row
    return {
        "phone_number": phone_number,
        "name": name,
        "notes": notes,
        "preferences": json.loads(preferences_json) if preferences_json else {},
        "updated_at": updated_at,
    }


def upsert_customer_profile(phone_number: str, name: str = None, notes: str = None, preferences: dict = None):
    """Create or update a customer's profile. Only overwrites fields that
    are actually passed in — existing values are preserved otherwise."""
    existing = get_customer_profile(phone_number) or {}

    final_name = name if name is not None else existing.get("name")
    final_notes = notes if notes is not None else existing.get("notes")

    final_preferences = existing.get("preferences", {}) or {}
    if preferences:
        final_preferences.update(preferences)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO customer_profiles (phone_number, name, notes, preferences, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(phone_number) DO UPDATE SET
            name = excluded.name,
            notes = excluded.notes,
            preferences = excluded.preferences,
            updated_at = CURRENT_TIMESTAMP
    """, (phone_number, final_name, final_notes, json.dumps(final_preferences)))
    conn.commit()
    conn.close()

    return get_customer_profile(phone_number)
