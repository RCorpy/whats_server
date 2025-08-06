import os
import subprocess
import requests
import uuid
import json
import asyncio
import mimetypes

from db import db
from dotenv import load_dotenv
from sse import connected_clients
from datetime import datetime

from PIL import Image
from io import BytesIO

load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")
YOUR_PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


def send_whatsapp_message(to, text=None, reaction=None, reply_to=None, media_type=None, media_url=None, media_filename=None, auto_save=False):

    if reaction:
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "reaction",
            "reaction": {
                "message_id": reply_to,
                "emoji": reaction
            }
        }
        content = f"[reaction] {reaction}"

    elif media_type and media_url:
        # Assume media_url is a local path to file, not a public link
        mime_type = get_mime_type(media_url)  # You can use mimetypes module
        media_id = upload_media_to_whatsapp(media_url, mime_type)
        
        if not media_id:
            print("❌ Failed to upload media to WhatsApp")
            return None

        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: {
                "id": media_id
            }
        }
        if media_type == "document" and media_filename:
            data[media_type]["filename"] = media_filename

        if reply_to:
            data["context"] = {"message_id": reply_to}

        content = f"[{media_type}] {media_filename or media_url}"

        if media_type == "document" and media_filename:
            data[media_type]["filename"] = media_filename

        if reply_to:
            data["context"] = {"message_id": reply_to}

        content = f"[{media_type}] {media_url}"


    else:
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text}
        }
        if reply_to:
            data["context"] = {"message_id": reply_to}
        content = text

    response = send_to_whatsapp_api(data)
    waba_id = extract_waba_message_id(response)
    if auto_save:
        save_message_to_db(
            to=to,
            sender="me",
            content=content,
            reference_id=reply_to,
            waba_id=waba_id
        )

    return response


# SEND MESSAGE PARTS

def send_to_whatsapp_api(data):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        print(f"📤 Sent to WhatsApp API | Status: {response.status_code} | {response.text}")
        return response
    except Exception as e:
        print(f"❌ Error sending to WhatsApp API: {e}")
        return None

def extract_waba_message_id(response):
    try:
        if response and response.status_code == 200:
            response_data = response.json()
            return response_data.get("messages", [{}])[0].get("id")
    except Exception as e:
        print(f"⚠️ Could not extract WABA message ID: {e}")
    return None

def save_message_to_db(to, sender, content, file=None, file_name=None, reference_id=None, waba_id=None):
    ensure_chat_exists(to)  # 💬 Make sure chat exists before saving the message

    message_id = str(uuid.uuid4())
    now_iso = datetime.utcnow()

    db_entry = {
        "_id": message_id,
        "chatWaId": to,
        "sender": sender,
        "content": content,
        "timestamp": {"$date": now_iso},
        "status": "sent",
        "file": file,
        "fileName": file_name,
        "referenceContent": reference_id
    }

    if waba_id:
        db_entry["wabaMessageId"] = waba_id

    db.messages.insert_one(db_entry)

    # Optionally update the chat with the last message and timestamp
    db.chats.update_one(
        {"waId": to},
        {
            "$set": {
                "lastMessage": content,
                "timestamp": {"$date": now_iso},
                "unreadCount": 0  # This might change if it's incoming
            }
        }
    )

    # Send to frontend
    payload = json.dumps(db_entry, default=str)
    for client in connected_clients:
        asyncio.create_task(await_safe_put(client, payload))

    return message_id




def convert_to_whatsapp_video(input_path: str, output_path: str):
    try:
        command = [
            "ffmpeg",
            "-i", input_path,
            "-vf", "scale=w=1280:h=720:force_original_aspect_ratio=decrease",
            "-c:v", "libx264",
            "-profile:v", "baseline",
            "-level", "3.0",
            "-preset", "fast",
            "-b:v", "1M",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "1",
            output_path
        ]
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e}")
        return False

def convert_audio_to_ogg(input_path, output_path):
    try:
        subprocess.run([
            "ffmpeg",
            "-y",  # Overwrite output if exists
            "-i", input_path,
            "-c:a", "libopus",  # ✅ Opus codec for WhatsApp
            "-b:a", "64k",      # Optional: audio bitrate
            "-vn",              # No video
            "-f", "ogg",        # Ensure Ogg container
            output_path
        ], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Audio conversion failed: {e}")
        return False

def ensure_chat_exists(wa_id, is_group=False, group_name=None):
    existing_chat = db.chats.find_one({"waId": wa_id})
    if existing_chat:
        return existing_chat["_id"]

    now_iso = datetime.utcnow()
    chat_data = {
        "_id": uuid.uuid4().hex,
        "waId": wa_id,
        "isGroup": is_group,
        "groupName": group_name,
        "lastMessage": "",
        "participants": [],
        "timestamp": {"$date": now_iso},
        "unreadCount": 0,
        "isTyping": False,
        "isMuted": False,
        "isPinned": False,
        "isBlocked": False
    }

    db.chats.insert_one(chat_data)
    print(f"💬 Created new chat with {wa_id}")
    return chat_data["_id"]



async def await_safe_put(client, data):
    try:
        await client.put(data)
    except Exception as e:
        print(f"⚠️ Failed to push to client: {e}")


def upload_media_to_whatsapp(file_path, mime_type):
    url = f"https://graph.facebook.com/v19.0/{os.getenv('PHONE_NUMBER_ID')}/media"  # Replace with actual phone number ID
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    with open(file_path, 'rb') as f:
        files = {
            'file': (os.path.basename(file_path), f, mime_type)
        }
        data = {
            'messaging_product': 'whatsapp',
            'type': mime_type
        }

        response = requests.post(url, headers=headers, files=files, data=data)
        print(f"📤 Upload media response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            return response.json().get('id')  # media_id
        return None


def get_mime_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'



def sanitize_image(image_bytes, output_path):
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            rgb_image = img.convert("RGB")  # Ensure RGB format
            rgb_image.save(output_path, format="JPEG", quality=85)
        return True
    except Exception as e:
        print(f"❌ Failed to sanitize image: {e}")
        return False