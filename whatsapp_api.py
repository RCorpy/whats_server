from fastapi import FastAPI, Request
from functions import send_whatsapp_message, ensure_chat_exists, save_message_to_db
from sse import push_to_clients

import mimetypes
import json
import requests
import os

WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")



def register_whatsapp_endpoints(app: FastAPI):
    @app.post("/webhook")
    async def receive_webhook(request: Request):
        try:
            body = await request.json()
            print("🔔 Received webhook payload:", body)

            entry = body["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            messages = value.get("messages", [])

            if not messages:
                return {"status": "no_message"}

            message = messages[0]
            from_number = message["from"]
            message_type = message["type"]

            ensure_chat_exists(from_number)

            file_path = None
            file_name = None
            content = None

            if message_type == "text":
                content = message["text"]["body"]

            elif message_type in ["image", "audio", "video", "document"]:
                media = message[message_type]
                print(f"📦 Media message received: {media}")

                media_id = media["id"]
                mime_type = media.get("mime_type", "application/octet-stream")
                file_name = media.get("filename", f"{media_id}.{mime_type.split('/')[-1]}")

                file_path = download_media(media_id, mime_type, file_name)
                content = f"[{message_type} received]"

            else:
                print(f"⚠️ Unsupported message type: {message_type}")
                return {"status": "unsupported_type"}

            # Save to DB
            save_message_to_db(
                to=from_number,
                sender="them",
                content=content,
                file=file_path,
                file_name=file_name,
                reference_id=message.get("id"),
                waba_id=value["metadata"]["phone_number_id"]
            )

            send_whatsapp_message(from_number, "✅ Message received!", auto_save=True)

        except Exception as e:
            print(f"❌ Error parsing webhook data: {e}")

        return {"status": "received"}




def download_media(media_id, mime_type=None, file_name=None):
    # 1. Get media URL
    media_url_response = requests.get(
        f"{WHATSAPP_API_URL}/{media_id}",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
    )

    if media_url_response.status_code != 200:
        print(f"❌ Failed to fetch media URL: {media_url_response.text}")
        return None

    media_url = media_url_response.json()["url"]

    # 2. Download file
    media_file_response = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
    )

    if media_file_response.status_code != 200:
        print(f"❌ Failed to download media: {media_file_response.text}")
        return None

    # 3. Guess MIME type and extension
    if not mime_type:
        mime_type = media_file_response.headers.get("Content-Type", "application/octet-stream")

    extension = mimetypes.guess_extension(mime_type.split(";")[0]) or ".bin"
    if extension.startswith("."):
        extension = extension[1:]

    # 4. Prepare save directory
    media_type_to_folder = {
        "image": "images",
        "video": "videos",
        "audio": "documents",   # ← audio goes with documents
        "document": "documents"
    }
    # Extract media type from MIME type if not directly provided
    # Example: mime_type = "image/jpeg" → media_category = "image"
    media_category = mime_type.split("/")[0] if mime_type else "documents"
    save_subdir = media_type_to_folder.get(media_category, "documents")

    save_dir = os.path.join("uploads", "temporalFiles", save_subdir)
    os.makedirs(save_dir, exist_ok=True)

    # 5. Filename handling
    base_name = file_name or f"{media_id}"
    base_name = os.path.splitext(base_name)[0]  # Remove any existing extension
    full_path = os.path.join(save_dir, f"{base_name}.{extension}")

    print(f"💾 Saving media to: {full_path} (type: {mime_type})")

    # 6. Save to disk
    with open(full_path, "wb") as f:
        f.write(media_file_response.content)

    return f"https://bricopoxi.com/{full_path}"
