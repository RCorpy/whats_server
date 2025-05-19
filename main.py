from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os

load_dotenv()  # carga variables del .env
app = FastAPI()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

@app.get("/")
async def root():
    return {f"message": f"Server is running! ACCESS TOKEN: {ACCESS_TOKEN} VERIFY TOKEN: {VERIFY_TOKEN} WHATSAPP API URL: {WHATSAPP_API_URL}"}

@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("Received webhook:", data)
    return {"status": "ok"}

