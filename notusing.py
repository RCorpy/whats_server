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