from fastapi import FastAPI, Request, HTTPException, Body, UploadFile, File, Form, Query, Path
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from bson import ObjectId
from dotenv import load_dotenv
from backend.routes import chats
import os
import requests
import shutil
import uuid
from pymongo import MongoClient
from pydantic import BaseModel


load_dotenv()
app = FastAPI()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL)
db = client["whatsapp"]


class ParticipantAction(BaseModel):
    groupWaId: str
    waId: str

@app.get("/")
async def root():
    return {
        "message": "Server is running!",
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "VERIFY_TOKEN": VERIFY_TOKEN,
        "WHATSAPP_API_URL": WHATSAPP_API_URL
    }

@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return params.get("hub.challenge")
    return "Invalid verify token"

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
    referenceContent: str = Form(None)
):
    try:

        # Check if chat is blocked
        chat = db.chats.find_one({"waId": chatId})
        if chat and chat.get("isBlocked") is True:
            print(f"⚠️ Message to blocked chat {chatId} ignored.")
            raise HTTPException(status_code=403, detail="This chat is blocked. Message not saved.")

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

        try:
            ts = datetime.fromtimestamp(float(timestamp) / 1000)
        except Exception:
            ts = datetime.utcnow()

        message_doc = {
            "_id": id,
            "chatWaId": chatId,
            "sender": senderId,
            "content": content.strip() or None,
            "timestamp": ts,
            "status": "sent",
            "file": file_url,
            "fileName": file_name,
            "referenceContent": referenceContent
        }

        db.messages.insert_one(message_doc)

        db.chats.update_one(
            {"waId": chatId},
            {
                "$set": {
                    "lastMessage": content or file_name,
                    "timestamp": ts,
                },
                "$inc": {"unreadCount": 1}
            },
            upsert=True
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
            "referenceContent": referenceContent
        }

    except Exception as e:
        print(f"❌ Error saving message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/chats")
async def get_chats_api():
    try:
        chats_cursor = db.chats.find().sort("timestamp", -1)
        contacts_map = {c["waId"]: c for c in db.contacts.find()}

        response_chats = []
        for chat_doc in chats_cursor:
            wa_id = chat_doc.get("waId")
            if not wa_id:
                continue
            is_group = chat_doc.get("isGroup", False)
            chat_name = "Unknown"
            chat_picture = None
            participants_list = []

            if is_group:
                chat_name = chat_doc.get("groupName", "Group Chat")
                chat_picture = chat_doc.get("groupPicture")
                raw_participants = chat_doc.get("participants", [])
                for p_raw in raw_participants:
                    p_contact = contacts_map.get(p_raw["waId"])
                    participants_list.append({
                        "waId": p_raw["waId"],
                        "name": p_contact.get("name") if p_contact else p_raw.get("name", p_raw["waId"]),
                        "isAdmin": p_raw.get("isAdmin", True)
                    })

            else:
                contact = contacts_map.get(wa_id)
                if contact:
                    chat_name = contact.get("name", "Unknown Contact")
                    chat_picture = contact.get("profilePic")
                else:
                    chat_name = wa_id

            timestamp_dt = chat_doc.get("timestamp", datetime.utcnow())

            response_chats.append({
                "id": wa_id,
                "name": chat_name,
                "picture": chat_picture,
                "lastMessage": chat_doc.get("lastMessage", ""),
                "timestamp": timestamp_dt.timestamp() * 1000,
                "unreadCount": chat_doc.get("unreadCount", 0),
                "isTyping": chat_doc.get("isTyping", False),
                "isGroup": is_group,
                "participants": participants_list if is_group else [],
                "isPinned": chat_doc.get("isPinned", False),
                "isMuted": chat_doc.get("isMuted", False),
                "isBlocked": chat_doc.get("isBlocked", False)
            })
        return response_chats

    except Exception as e:
        print(f"Error in /api/chats: {e}")
        import traceback
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
            "fileName": msg.get("fileName"),
            "referencedContent": msg.get("referenceContent"),
            "reactions": msg.get("reactions", [])
        })

    db.chats.update_one(
        {"waId": chat_id},
        {"$set": {"unreadCount": 0}}
    )
    return messages

def send_whatsapp_message(to, text, message_db_id=None):
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
    
    if response.status_code == 200:
        try:
            response_data = response.json()
            waba_message_id = response_data.get("messages", [{}])[0].get("id")
            if waba_message_id and message_db_id:
                db.messages.update_one(
                    {"_id": message_db_id},
                    {"$set": {"wabaMessageId": waba_message_id, "status": "sent_to_waba"}}
                )
                print(f"Stored WABA message ID {waba_message_id} for DB message {message_db_id}")
        except Exception as e:
            print(f"Error parsing WABA response or updating DB with waba_message_id: {e}")
    return response

@app.post("/api/messages/react")
async def react_to_message(data: dict = Body(...)):
    message_id = data.get("messageId")
    requester_id = data.get("requesterId")
    emoji = data.get("emoji")
    chat_id = data.get("chatId")  # Por si lo necesitas luego

    if not message_id or not requester_id or not emoji:
        raise HTTPException(status_code=400, detail="Missing fields")

    try:
        # Verificamos que el mensaje exista
        message = db.messages.find_one({"_id": message_id})
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Eliminamos reacción previa del mismo usuario, si existe
        db.messages.update_one(
            {"_id": message_id},
            {"$pull": {"reactions": {"user": requester_id}}}
        )

        # Añadimos la nueva reacción
        db.messages.update_one(
            {"_id": message_id},
            {"$push": {"reactions": {"user": requester_id, "emoji": emoji}}}
        )

        return {"success": True, "message": "Reaction updated"}

    except Exception as e:
        print(f"❌ Error updating reaction: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/chat/pin")
async def pin_unpin_chat(data: dict = Body(...)):
    try:
        waId = data.get("waId")
        if not waId:
            raise HTTPException(status_code=400, detail="Missing waId")

        chat_doc = db.chats.find_one({"waId": waId})
        if not chat_doc:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Obtener valor actual o False si no existe
        is_pinned = chat_doc.get("isPinned", False)

        # Invertir pin
        result = db.chats.update_one(
            {"waId": waId},
            {"$set": {
                "isPinned": not is_pinned,
            }}
        )
        return {"success": True, "isPinned": not is_pinned}

    except HTTPException:
        raise  # Re-lanza excepciones HTTP personalizadas
    except Exception as e:
        print(f"❌ Error in pin_unpin_chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



@app.post("/api/chat/mute")
async def mute_unmute_chat(data: dict = Body(...)):
    try:
        waId = data.get("waId")
        if not waId:
            raise HTTPException(status_code=400, detail="Missing waId")

        chat_doc = db.chats.find_one({"waId": waId})
        if not chat_doc:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Obtener valor actual o False si no existe
        is_muted = chat_doc.get("isMuted", False)

        # Invertir mute, mantener el valor de pin
        result = db.chats.update_one(
            {"waId": waId},
            {"$set": {
                "isMuted": not is_muted,
            }}
        )
        return {"success": True, "isMuted": not is_muted}

    except HTTPException:
        raise  # Re-lanza excepciones HTTP personalizadas
    except Exception as e:
        print(f"❌ Error in mute_unmute_chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/chat/block")
async def mute_unmute_chat(data: dict = Body(...)):
    try:
        waId = data.get("waId")
        if not waId:
            raise HTTPException(status_code=400, detail="Missing waId")

        chat_doc = db.chats.find_one({"waId": waId})
        if not chat_doc:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Obtener valor actual o False si no existe
        is_blocked = chat_doc.get("isBlocked", False)

        print("isBlocked: ", is_blocked, " not blocked: ", not is_blocked)
        # Invertir block, mantener el valor de pin
        result = db.chats.update_one(
            {"waId": waId},
            {"$set": {
                "isBlocked": not is_blocked,
            }}
        )
        return {"success": True, "isBlocked": not is_blocked}

    except HTTPException:
        raise  # Re-lanza excepciones HTTP personalizadas
    except Exception as e:
        print(f"❌ Error in mute_unmute_chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/contacts")
async def get_contacts():
    try:
        contact_docs = list(db.contacts.find())
        contacts = []

        for c in contact_docs:
            contacts.append({
                "id": c["waId"],
                "name": c.get("name", "Unknown"),
                "profilePic": c.get("profilePic"),
                "isOnline": c.get("isOnline", False),
                "lastSeen": c.get("lastSeen")
            })

        return contacts
    except Exception as e:
        print(f"Error in /api/contacts: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/chat/add-participant")
def add_participant(data):
    participant = {
        "waId": data.participantWaId,
        "name": data.participantName or "Unknown",
        "isAdmin": False,  # Puedes añadir más campos si quieres
    }
    result = db.chats.update_one(
        {"waId": data.groupWaId},
        {"$addToSet": {"participants": participant}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"status": "participant added", "chatWaId": data.groupWaId, "participant": participant}

@app.post("/api/chat/remove-participant")
def remove_participant(data):
    print(data)
    result = db.chats.update_one(
        {"waId": data.groupWaId},
        {"$pull": {"participants": {"waId": data.participantWaId}}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"status": "participant removed", "chatWaId": data.groupWaId, "participantWaId": data.participantWaId}





@app.get("/api/newcontact")
def save_contact_file():
    contact_doc = {
        "_id": f"{uuid.uuid4().hex}",
        "waId": "521234567891",
        "name": "Ron Reymon",
        "profilePic": "https://example.com/pic.jpg",
        "isOnline": True,
        "lastSeen": datetime.utcnow()
    }
    db.contacts.insert_one(contact_doc)
    return {"status": "inserted", "contact": contact_doc}

@app.get("/api/newchat")
def save_chat_file():
    chat_doc = {
        "_id": f"{uuid.uuid4().hex}",
        "waId": "521234567892",
        "isGroup": True,
        "groupName": "New group",
        "lastMessage": "",
        "participants": [],
        "timestamp": datetime.utcnow(),
        "unreadCount": 0,
        "isTyping": False
    }
    db.chats.insert_one(chat_doc)
    return {"status": "inserted", "chat": chat_doc}

@app.get("/api/newmessage")
def save_message_file():
    message_doc = {
        "_id": f"{uuid.uuid4().hex}",
        "chatWaId": "521234567892",
        "sender": "521234567891",
        "content": "Hello from /api/newmessage",
        "timestamp": datetime.utcnow(),
        "status": "sent"
    }
    db.messages.insert_one(message_doc)
    return {"status": "inserted", "message": message_doc}

@app.post("/api/chat/add-participant/{waId}")
async def add_participant(
    waId: str,
    groupWaId: str = Query(...)
):
    chat_doc = db.chats.find_one({"waId": groupWaId})
    if not chat_doc:
        raise HTTPException(status_code=404, detail="Group chat not found")
    if not chat_doc.get("isGroup", False):
        raise HTTPException(status_code=400, detail="This is not a group chat")

    # Buscar contacto en contacts
    contact = db.contacts.find_one({"waId": waId})
    if not contact:
        # Opcional: devolver error si no se encuentra el contacto
        raise HTTPException(status_code=404, detail="Contact not found")

    participant_data = {
        "waId": contact["waId"],
        "name": contact.get("name", ""),
        "profilePic": contact.get("profilePic", "")
    }

    # Evitar añadir duplicados
    for p in chat_doc.get("participants", []):
        if p.get("waId") == waId:
            return {"success": False, "message": "Participant already in group"}

    updated = db.chats.update_one(
        {"waId": groupWaId},
        {"$push": {"participants": participant_data}}
    )

    if updated.modified_count == 0:
        return {"success": False, "message": "Failed to add participant"}

    return {"success": True, "message": "Participant added", "participant": participant_data}


@app.post("/api/chat/remove-participant/{waId}")
async def remove_participant(
    waId: str = Path(..., description="ID del participante a eliminar"),
    groupWaId: str = Query(..., description="ID del grupo")
):
    # Aquí ya tienes ambos valores disponibles
    chat_doc = db.chats.find_one({"waId": groupWaId})
    if not chat_doc:
        raise HTTPException(status_code=404, detail="Group chat not found")
    if not chat_doc.get("isGroup", False):
        raise HTTPException(status_code=400, detail="This is not a group chat")

    updated = db.chats.update_one(
        {"waId": groupWaId},
        {"$pull": {"participants": {"waId": waId}}}
    )

    if updated.modified_count == 0:
        return {"success": False, "message": "Participant not found in group"}

    return {"success": True, "message": "Participant removed"}

@app.post("/api/messages/delete")
async def delete_message(data: dict = Body(...)):
    try:
        message_id = data.get("messageId")
        requester_id = data.get("requesterId")

        if not message_id or not requester_id:
            raise HTTPException(status_code=400, detail="Missing messageId or requesterId")

        message = db.messages.find_one({"_id": message_id})

        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        if message["sender"] != requester_id:
            raise HTTPException(status_code=403, detail="You can only delete your own messages")

        # ✨ En vez de eliminarlo, lo actualizamos
        db.messages.update_one(
            {"_id": message_id},
            {"$set": {
                "content": "Este mensaje se ha borrado",
                "file": None,
                "referenceContent": None
            }}
        )

        return {"success": True, "message": "Message marked as deleted"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
