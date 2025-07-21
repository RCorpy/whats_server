from fastapi import FastAPI, Request

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
                text = message["text"]["body"]
                print(f"Message from {from_number}: {text}")

                send_whatsapp_message(from_number, "✅ Message received! Thanks for contacting us.")

        except Exception as e:
            print(f"❌ Error parsing webhook data: {e}")

        return {"status": "received"}