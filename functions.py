import os
import subprocess

from db import db

def register_functions():
    pass

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