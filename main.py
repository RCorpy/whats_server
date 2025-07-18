from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv


from pydantic import BaseModel

from get_endpoints import register_get_endpoints
from post_endpoints import register_post_endpoints
from whatsapp_api import register_whatsapp_endpoints
from functions import register_functions

#imports for force

from datetime import datetime
from db import db
import uuid

load_dotenv()
app = FastAPI()

register_get_endpoints(app)
register_post_endpoints(app)
register_whatsapp_endpoints(app)
register_functions()

@app.get("/api/forcenewcontact")
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

@app.get("/api/forcenewchat")
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

@app.get("/api/forcenewmessage")
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






app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
