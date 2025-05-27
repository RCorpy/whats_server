# db.py

from pymongo import MongoClient

# Replace with your real MongoDB URI
MONGO_URI = "mongodb://localhost:27017"
# Or if using authentication:
# MONGO_URI = "mongodb://username:password@host:port"

client = MongoClient(MONGO_URI)
db = client["whatsapp"]

# Optional: Define collections
contacts_collection = db["contacts"]
chats_collection = db["chats"]
messages_collection = db["messages"]
users_collection = db["users"]
