import os
import subprocess
import requests
import uuid


from db import db
from dotenv import load_dotenv
from sse import connected_clients
from datetime import datetime

load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")


def send_whatsapp_message(to, text=None, reaction=None, reply_to=None):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

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
    else:
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text}
        }
        if reply_to:
            data["context"] = {"message_id": reply_to}

    try:
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        print(f"📤 Sent to {to} | Status: {response.status_code} | {response.text}")
    except Exception as e:
        print(f"❌ Failed to send message to {to}: {e}")
        return None

    if response.status_code == 200:
        try:
            message_id = str(uuid.uuid4())
            now_iso = datetime.utcnow().isoformat() + "Z"

            db_entry = {
                "_id": message_id,
                "chatWaId": to,
                "sender": "me",
                "content": None if reaction else text,
                "timestamp": {"$date": now_iso},
                "status": "sent",
                "file": None,
                "fileName": None,
                "referenceContent": reply_to if reply_to else None
            }

            if reaction:
                db_entry["content"] = f"[reaction] {reaction}"

            db.messages.insert_one(db_entry)

            # Send to frontend
            payload = json.dumps(db_entry, default=str)
            for client in connected_clients:
                asyncio.create_task(await_safe_put(client, payload))

            return response

        except Exception as e:
            print(f"⚠️ Could not save or broadcast message: {e}")
    return response


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
            "-c:a", "libvorbis",  # OGG encoding
            output_path
        ], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Audio conversion failed: {e}")
        return False








