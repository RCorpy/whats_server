from fastapi import FastAPI, Request, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from bson import ObjectId
from dotenv import load_dotenv
from backend.routes import chats
import os
import requests  # pip install requests
import shutil
import uuid
from pymongo import MongoClient

load_dotenv()
app = FastAPI()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL)
db = client["whatsapp"]

@app.get("/")
async def root():
    return {
        "message": "Server is running!",
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "VERIFY_TOKEN": VERIFY_TOKEN,
        "WHATSAPP_API_URL": WHATSAPP_API_URL
    }


# Webhook verification for Meta setup
@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return params.get("hub.challenge")
    return "Invalid verify token"


# Webhook receiver for incoming messages
@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        body = await request.json()
        print("🔔 Received webhook payload:", body)

        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])

        if messages:
            message = messages[0]
            from_number = message["from"]
            text = message["text"]["body"]
            print(f"Message from {from_number}: {text}")

            # Auto-reply
            send_whatsapp_message(from_number, "✅ Message received! Thanks for contacting us.")

    except Exception as e:
        print(f"❌ Error parsing webhook data: {e}")

    return {"status": "received"}

@app.post("/api/messages")
async def save_message_file(
    id: str = Form(...),
    chatId: str = Form(...),
    senderId: str = Form(...),
    content: str = Form(""),
    timestamp: str = Form(...),
    file: UploadFile = File(None),
    referenceId: str = Form(None)
):
    try:
        file_url = None
        file_name = None

        if file:
            os.makedirs("uploads/messages", exist_ok=True)
            file_name = file.filename
            unique_name = f"{uuid.uuid4().hex}_{file.filename}"
            file_path = os.path.join("uploads/messages", unique_name)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            file_url = f"https://bricopoxi.com/uploads/messages/{unique_name}"

        # Convert timestamp to datetime
        try:
            ts = datetime.fromtimestamp(float(timestamp) / 1000)
        except Exception:
            ts = datetime.utcnow()

        message_doc = {
            "_id": id,  # Use client-generated ID directly
            "chatWaId": chatId,
            "sender": senderId,
            "content": content.strip() or None,
            "timestamp": ts,
            "status": "sent",
            "file": file_url,
            "fileName": file_name,
            "referenceId": referenceId
        }

        db.messages.insert_one(message_doc)

        db.chats.update_one(
            {"contactWaId": chatId},
            {
                "$set": {
                    "lastMessage": content or file_name,
                    "timestamp": ts,
                },
                "$inc": {"unreadCount": 1}
            },
            upsert=True  # 👈 In case chat does not exist
        )

        return {
            "id": id,
            "chatId": chatId,
            "senderId": senderId,
            "content": content,
            "timestamp": ts.timestamp() * 1000,
            "status": "sent",
            "file": file_url,
            "fileName": file_name,
            "referenceId": referenceId
        }

    except Exception as e:
        print(f"❌ Error saving message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/chats")
async def get_chats():
    try:
        chats_cursor = db.chats.find()
        contacts = {c["waId"]: c for c in db.contacts.find()}

        chats = []
        for chat in chats_cursor:
            waId = chat.get("contactWaId")
            if not waId:
                continue

            contact = contacts.get(waId, {})
            timestamp = chat.get("timestamp", datetime.utcnow())

            chats.append({
                "id": waId,
                "name": contact.get("name", "Unknown"),
                "picture": contact.get("profilePic"),
                "lastMessage": chat.get("lastMessage", ""),
                "timestamp": timestamp.timestamp() * 1000,
                "unreadCount": chat.get("unreadCount", 0),
                "isTyping": chat.get("isTyping", False),
            })
        return chats

    except Exception as e:
        print("Error in /api/chats:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/api/messages/{chat_id}")
async def get_messages(chat_id: str):
    messages_cursor = db.messages.find({"chatWaId": chat_id})

    messages = []
    for msg in messages_cursor:
        messages.append({
          "id": str(msg["_id"]),
          "chatId": msg["chatWaId"],
          "senderId": msg["sender"],
          "content": msg.get("content"),
          "timestamp": msg["timestamp"].timestamp() * 1000,
          "status": msg["status"],
          "file": msg.get("file"),
          "fileName": msg.get("fileName")  # 👈 Add this
      })


    db.chats.update_one(
        {"contactWaId": chat_id},
        {"$set": {"unreadCount": 0}}
    )
    return messages


def send_whatsapp_message(to, text):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
    print(f"Sent message to {to}, response: {response.status_code} - {response.text}")


app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")