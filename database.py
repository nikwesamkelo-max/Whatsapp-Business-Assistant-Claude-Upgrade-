"""
database.py — upgraded with phone_number tracking + a bookings table.

Changes from your original:
- `messages` table now has a `phone_number` column, so each customer's
  conversation is separate.
- New `bookings` table so start_booking() can persist real bookings,
  not just simulate them.
- Added `created_at` timestamps for both tables.
- get_all_messages() now supports an optional phone_number filter but
  still returns everything if you don't pass one, so nothing breaks.
"""

import sqlite3

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

    conn.commit()
    conn.close()


# ---------- Messages ----------

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
    """Returns all messages, or just one customer's if phone_number is given."""
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
    """Most recent N messages for one customer, oldest first — used to
    build conversation history for Claude."""
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


# ---------- Bookings ----------

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
