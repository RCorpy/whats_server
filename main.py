from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import PlainTextResponse
from datetime import datetime
from bson import ObjectId
from dotenv import load_dotenv
from backend.routes import chats
import os
import requests  # pip install requests
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
async def save_message(request: Request):
    try:
        data = await request.json()
        # Validar campos mínimos
        required_fields = ["chatId", "senderId", "content"]
        for f in required_fields:
            if f not in data:
                raise HTTPException(status_code=400, detail=f"Missing field: {f}")

        message_doc = {
            "chatWaId": data["chatId"],
            "sender": data["senderId"],
            "content": data["content"],
            "timestamp": datetime.utcnow(),
            "status": data.get("status", "sent"),  # por defecto "sent"
        }

        result = db.messages.insert_one(message_doc)
        message_doc["_id"] = result.inserted_id
        # Actualizar el chat con el último mensaje y timestamp
        db.chats.update_one(
            {"contactWaId": data["chatId"]},
            {
                "$set": {
                    "lastMessage": data["content"],
                    "timestamp": message_doc["timestamp"],
                },
                "$inc": {
                    "unreadCount": 1
                }
            }
        )

        # Devolver el mensaje guardado con ID y timestamp en milisegundos
        return {
            "id": str(message_doc["_id"]),
            "chatId": message_doc["chatWaId"],
            "senderId": message_doc["sender"],
            "content": message_doc["content"],
            "timestamp": message_doc["timestamp"].timestamp() * 1000,
            "status": message_doc["status"],
        }

    except Exception as e:
        print(f"❌ Error saving message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/send")
async def send_message(request: Request):
    body = await request.json()
    to = body.get("to")
    text = body.get("text")
    send_whatsapp_message(to, text)
    return {"status": "message sent"}

@app.get("/api/chats")
async def get_chats():
    chats_cursor = db.chats.find()
    contacts = {c["waId"]: c for c in db.contacts.find()}

    chats = []
    for chat in chats_cursor:
        waId = chat["contactWaId"]
        contact = contacts.get(waId, {})
        chats.append({
            "id": waId,
            "name": contact.get("name", "Unknown"),
            "picture": contact.get("profilePic"),
            "lastMessage": chat.get("lastMessage"),
            "timestamp": chat.get("timestamp").timestamp() * 1000,
            "unreadCount": chat.get("unreadCount", 0),
            "isTyping": chat.get("isTyping", False),
        })
    return chats

@app.get("/api/messages/{chat_id}")
async def get_messages(chat_id: str):
    messages_cursor = db.messages.find({"chatWaId": chat_id})

    messages = []
    for msg in messages_cursor:
        messages.append({
            "id": str(msg["_id"]),
            "chatId": msg["chatWaId"],
            "senderId": msg["sender"],
            "content": msg["content"],
            "timestamp": msg["timestamp"].timestamp() * 1000,
            "status": msg["status"]
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

