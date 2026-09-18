import base64

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse

import assistant
import database

app = FastAPI()

database.init_db()


@app.get("/")
def home():
    return {"message": "WhatsApp Business Assistant is running \U0001f680"}


@app.get("/message")
def message(phone_number: str, text: str):
    response = assistant.process_message(phone_number, text)
    return {
        "phone_number": phone_number,
        "user_message": text,
        "bot_response": response,
    }


@app.get("/message/managed")
def message_managed(phone_number: str, text: str):
    """Same conversation, routed through Claude Managed Agents instead of
    the manual tool-use loop - see managed_assistant.py. Requires
    setup_managed_agent.py to have been run first."""
    import managed_assistant
    try:
        response = managed_assistant.process_message_managed(phone_number, text)
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "phone_number": phone_number,
        "user_message": text,
        "bot_response": response,
        "mode": "managed_agents",
    }


@app.post("/message/image")
async def message_with_image(
    phone_number: str = Form(...),
    text: str = Form(...),
    image: UploadFile = File(...),
):
    """Multimodal endpoint - customer sends a photo (e.g. their venue)
    alongside a text message. No extra ML dependencies: Claude does the
    actual image reasoning, this just base64-encodes the upload."""
    image_bytes = await image.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    response = assistant.process_message(
        phone_number,
        text,
        image_base64=image_base64,
        image_media_type=image.content_type or "image/jpeg",
    )
    return {
        "phone_number": phone_number,
        "user_message": text,
        "image_filename": image.filename,
        "bot_response": response,
    }


@app.get("/message/stream")
def message_stream(phone_number: str, text: str):
    """Streams the reply chunk-by-chunk instead of waiting for the full
    response. Test with: curl --no-buffer "http://.../message/stream?..." """
    def event_generator():
        for chunk in assistant.process_message_stream(phone_number, text):
            yield chunk

    return StreamingResponse(event_generator(), media_type="text/plain")


@app.get("/history")
def history(phone_number: str | None = None):
    data = database.get_all_messages(phone_number)
    return {"phone_number": phone_number, "total_messages": len(data), "messages": data}


@app.get("/bookings")
def bookings(phone_number: str | None = None):
    data = database.get_bookings(phone_number)
    return {"phone_number": phone_number, "total_bookings": len(data), "bookings": data}


@app.get("/profile")
def profile(phone_number: str):
    return {"phone_number": phone_number, "profile": database.get_customer_profile(phone_number)}


@app.get("/analytics")
def analytics(phone_number: str | None = None):
    """Structured interaction data from classify_interaction - category,
    sentiment, and urgency per message, ready for a dashboard later."""
    logs = database.get_interaction_logs(phone_number)
    return {"phone_number": phone_number, "total_logged": len(logs), "logs": logs}
