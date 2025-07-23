from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware


from pydantic import BaseModel

from get_endpoints import register_get_endpoints
from post_endpoints import register_post_endpoints
from whatsapp_api import register_whatsapp_endpoints
from sse import push_to_clients

#imports for force

from datetime import datetime
from db import db
import uuid
import asyncio

from sse import connected_clients

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_get_endpoints(app)
register_post_endpoints(app)
register_whatsapp_endpoints(app)


@app.get("/sse")
async def sse_endpoint(request: Request):
    queue = asyncio.Queue()
    connected_clients.append(queue)

    async def event_stream():
        print("event_streaming")
        try:
            #yield "retry: 10000\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # 🔁 Send heartbeat to keep connection alive
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            print("💤 Client disconnected")
        finally:
            connected_clients.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
