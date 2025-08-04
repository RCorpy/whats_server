from fastapi import FastAPI, Request
from functions import send_whatsapp_message, ensure_chat_exists, save_message_to_db
from sse import push_to_clients

import json





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

            if messages:
                message = messages[0]
                from_number = message["from"]
                #print("look for this", from_number, waba_id)
                #if from_number == waba_id:
                #    print("↩️ Ignored own outgoing message echoed back from WhatsApp.")
                #    return {"status": "ignored"}
                text = message["text"]["body"]

                print(f"💬 Incoming message from {from_number}: {text}")

                ensure_chat_exists(from_number)  # ✅ ensure the chat exists before processing

                save_message_to_db(
                    to=from_number,
                    sender="them",
                    content=text,
                    file=None,
                    file_name=None,
                    reference_id=None,
                    waba_id=message["id"] if "id" in message else None
                )
                # Optional auto-reply
                send_whatsapp_message(from_number, "✅ Message received! Thanks for contacting us.", auto_save=True)

        except Exception as e:
            print(f"❌ Error parsing webhook data: {e}")

        return {"status": "received"}



