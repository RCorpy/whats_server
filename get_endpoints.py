from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from datetime import datetime

from db import db

import os

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

def register_get_endpoints(app: FastAPI):
    @app.get("/")
    async def root():
        return {
            "message": "Server is running!",
            "ACCESS_TOKEN": ACCESS_TOKEN,
            "VERIFY_TOKEN": VERIFY_TOKEN,
            "WHATSAPP_API_URL": WHATSAPP_API_URL
        }

    @app.get("/download/{file_name}")
    def download_file(file_name: str):
        print("downloading?")
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "messages")
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        if not os.path.exists(file_path):
            UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "temporalFiles")
            REAL_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "documents")
            file_path = os.path.join(REAL_UPLOAD_DIR, file_name)

            if not os.path.exists(file_path):
                REAL_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "images")
                file_path = os.path.join(REAL_UPLOAD_DIR, file_name)

                if not os.path.exists(file_path):
                    REAL_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "videos")
                    file_path = os.path.join(REAL_UPLOAD_DIR, file_name)

                    if not os.path.exists(file_path):
                        UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "permanentFiles")
                        file_path = os.path.join(UPLOAD_DIR, file_name)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found at {file_path}")
        
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={file_name}"}
        )

    @app.get("/webhook", response_class=PlainTextResponse)
    async def verify_webhook(request: Request):
        params = request.query_params
        if params.get("hub.verify_token") == VERIFY_TOKEN:
            return params.get("hub.challenge")
        return "Invalid verify token"

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

                timestamp_raw = chat_doc.get("timestamp", datetime.utcnow())
                if isinstance(timestamp_raw, datetime):
                    timestamp_dt = timestamp_raw

                elif isinstance(timestamp_raw, dict) and "$date" in timestamp_raw:
                    try:
                        timestamp_dt = datetime.fromisoformat(timestamp_raw["$date"].replace("Z", "+00:00"))
                    except Exception:
                        timestamp_dt = datetime.utcnow()  # fallback if parsing fails

                elif isinstance(timestamp_raw, str):
                    try:
                        timestamp_dt = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                    except Exception:
                        timestamp_dt = datetime.utcnow()  # fallback if parsing fails

                else:
                    timestamp_dt = datetime.utcnow()  # final fallback

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

    from datetime import datetime

    @app.get("/api/messages/{chat_id}")
    async def get_messages(chat_id: str):
        messages_cursor = db.messages.find({"chatWaId": chat_id})

        messages = []
        for msg in messages_cursor:
            # Fix timestamp parsing
            timestamp_raw = msg.get("timestamp", datetime.utcnow())
            if isinstance(timestamp_raw, datetime):
                timestamp_dt = timestamp_raw

            elif isinstance(timestamp_raw, dict) and "$date" in timestamp_raw:
                try:
                    timestamp_dt = datetime.fromisoformat(timestamp_raw["$date"].replace("Z", "+00:00"))
                except Exception:
                    timestamp_dt = datetime.utcnow()  # fallback if parsing fails

            elif isinstance(timestamp_raw, str):
                try:
                    timestamp_dt = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
                except Exception:
                    timestamp_dt = datetime.utcnow()  # fallback if parsing fails

            else:
                timestamp_dt = datetime.utcnow()  # final fallback

            messages.append({
                "id": str(msg["_id"]),
                "chatId": msg["chatWaId"],
                "senderId": msg["sender"],
                "content": msg.get("content"),
                "timestamp": int(timestamp_dt.timestamp() * 1000),
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