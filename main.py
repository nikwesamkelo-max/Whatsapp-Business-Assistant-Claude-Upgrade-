from fastapi import FastAPI
from assistant import process_message
from database import init_db, get_all_messages, get_bookings, save_message

app = FastAPI()

# Initialize database when server starts
init_db()


@app.get("/")
def home():
    return {"message": "WhatsApp Business Assistant is running 🚀"}


@app.get("/message")
def message(phone_number: str, text: str):
    # 1. Process message through the Claude-powered assistant brain
    response = process_message(phone_number, text)

    # 2. Save to SQLite, tied to this customer's phone number
    save_message(phone_number, text, response)

    # 3. Return response (simulating WhatsApp reply)
    return {
        "phone_number": phone_number,
        "user_message": text,
        "bot_response": response,
    }


@app.get("/history")
def history(phone_number: str | None = None):
    # Optional phone_number filter; omit it to see every conversation
    data = get_all_messages(phone_number)
    return {
        "phone_number": phone_number,
        "total_messages": len(data),
        "messages": data,
    }


@app.get("/bookings")
def bookings(phone_number: str | None = None):
    data = get_bookings(phone_number)
    return {
        "phone_number": phone_number,
        "total_bookings": len(data),
        "bookings": data,
    }
