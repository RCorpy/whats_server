from fastapi import FastAPI, Form, File, UploadFile, HTTPException, Body, Query, Path
from datetime import datetime

from functions import convert_to_whatsapp_video, convert_audio_to_ogg, send_whatsapp_message, sanitize_image
from db import db


import hashlib
import os
import magic
import subprocess
import json

def register_post_endpoints(app: FastAPI):
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

        def is_audio_only_webm(file_path):
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", file_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                streams = json.loads(result.stdout).get("streams", [])
                video_streams = [s for s in streams if s.get("codec_type") == "video"]
                audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
                return len(video_streams) == 0 and len(audio_streams) > 0
            except Exception as e:
                print(f"ffprobe error: {e}")
                return False

        try:
            # Check if the messsage
            # Check if chat is blocked
            chat = db.chats.find_one({"waId": chatId})
            if chat and chat.get("isBlocked") is True:
                print(f"⚠️ Message to blocked chat {chatId} ignored.")
                raise HTTPException(status_code=403, detail="This chat is blocked. Message not saved.")


            file_url = None
            file_name = None

            if file:
                file_bytes = await file.read()
                print(f"Uploaded file size: {len(file_bytes)} bytes")
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                mime_type = magic.from_buffer(file_bytes, mime=True)

                print("MIMETYPE", mime_type)

                # Prepare file paths
                permanent_dir = os.path.join("uploads", "permanentFiles")
                base_temp_dir = os.path.join("uploads", "temporalFiles")
                os.makedirs(permanent_dir, exist_ok=True)
                os.makedirs(base_temp_dir, exist_ok=True)

                # Use the hash and original extension for naming
                ext = os.path.splitext(file.filename)[1]
                unique_name = f"{file_hash}{ext}"

                # Check for existing file
                permanent_path = os.path.join(permanent_dir, unique_name)
                if os.path.exists(permanent_path):
                    file_url = f"https://bricopoxi.com/uploads/permanentFiles/{unique_name}"
                else:
                    # Temporarily save file for probe
                    probe_temp_path = os.path.join(base_temp_dir, f"{file_hash}_probe{ext}")
                    with open(probe_temp_path, "wb") as f:
                        f.write(file_bytes)

                    # Determine category
                    if mime_type.startswith("image/"):
                        category = "images"
                        temp_dir = os.path.join(base_temp_dir, category)
                        os.makedirs(temp_dir, exist_ok=True)

                        sanitized_name = f"{file_hash}.jpg"
                        sanitized_path = os.path.join(temp_dir, sanitized_name)

                        success = sanitize_image(file_bytes, sanitized_path)

                        if success:
                            unique_name = sanitized_name
                            temp_path = sanitized_path
                        else:
                            print("⚠️ Falling back to original image without sanitization.")
                            fallback_path = os.path.join(temp_dir, unique_name)
                            with open(fallback_path, "wb") as f:
                                f.write(file_bytes)
                            temp_path = fallback_path


                    elif mime_type.startswith("video/"):
                        if is_audio_only_webm(probe_temp_path):
                            print("🎧 Detected audio-only file (video/webm with only audio stream)")
                            category = "documents"
                        else:
                            category = "videos"
                    elif mime_type.startswith("audio/"):
                        category = "documents"
                    else:
                        category = "documents"

                    os.remove(probe_temp_path)

                    temp_dir = os.path.join(base_temp_dir, category)
                    os.makedirs(temp_dir, exist_ok=True)

                    temp_path = os.path.join(temp_dir, unique_name)

                    # Save file if not already saved
                    if not os.path.exists(temp_path):
                        with open(temp_path, "wb") as f:
                            f.write(file_bytes)

                        # If it's a video, convert it
                        if category == "videos":
                            converted_path = os.path.join(temp_dir, f"{file_hash}_whatsapp.mp4")
                            success = convert_to_whatsapp_video(temp_path, converted_path)

                            if success and os.path.exists(converted_path):
                                os.remove(temp_path)  # Remove original
                                final_path = os.path.join(temp_dir, f"{file_hash}.mp4")
                                os.replace(converted_path, final_path)
                                temp_path = final_path
                                unique_name = f"{file_hash}.mp4"

                        # If it's audio, convert to .ogg
                        elif mime_type.startswith("audio/") or (mime_type == "video/webm" and category == "documents"):
                            print("AUDIO DETECTED")
                            temp_path = os.path.join(temp_dir, f"{file_hash}{ext}")
                            with open(temp_path, "wb") as f:
                                f.write(file_bytes)

                            final_name = f"{file_hash}.ogg"
                            final_path = os.path.join(temp_dir, final_name)
                            success = convert_audio_to_ogg(temp_path, final_path)

                            if success:
                                os.remove(temp_path)
                                unique_name = final_name

                    file_url = f"https://bricopoxi.com/uploads/temporalFiles/{category}/{unique_name}"
                    local_file_path = os.path.join("uploads", "temporalFiles", category, unique_name)
                    file_name = file.filename

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
            
            # Send the message to the WhatsApp API
            try:
                if file_url:
                    # Determine media type from file extension
                    if file_url.endswith(('.jpg', '.jpeg', '.png')):
                        media_type = "image"
                    elif file_url.endswith('.mp4'):
                        media_type = "video"
                    elif file_url.endswith('.ogg'):
                        media_type = "audio"
                    else:
                        media_type = "document"

                    send_whatsapp_message(
                        to=chatId,
                        media_type=media_type,
                        media_url=local_file_path,
                        media_filename=file_name
                    )
                elif content:
                    send_whatsapp_message(
                        to=chatId,
                        text=content
                    )
            except Exception as e:
                print(f"❌ Failed to send message to WhatsApp API: {e}")


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


    
