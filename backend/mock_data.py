# mock_data.py

from backend.db import contacts_collection, chats_collection, messages_collection
from datetime import datetime

waId = "521234567890"

# Clean previous
contacts_collection.delete_many({})
chats_collection.delete_many({})
messages_collection.delete_many({})

# Insert mock contact
contacts_collection.insert_one({
    "waId": waId,
    "name": "Juan Pérez",
    "profilePic": "https://example.com/pic.jpg",
    "isOnline": True,
    "lastSeen": datetime.utcnow()
})

# Insert chat
chats_collection.insert_one({
    "contactWaId": waId,
    "lastMessage": "¿Ya comiste?",
    "timestamp": datetime.utcnow(),
    "unreadCount": 2,
    "isTyping": False
})

# Insert messages
messages_collection.insert_many([
    {
        "chatWaId": waId,
        "sender": "me",
        "content": "Hola, ¿cómo estás?",
        "timestamp": datetime.utcnow(),
        "status": "read"
    },
    {
        "chatWaId": waId,
        "sender": waId,
        "content": "¿Ya comiste?",
        "timestamp": datetime.utcnow(),
        "status": "delivered"
    }
])

print("✅ Test data inserted.")
