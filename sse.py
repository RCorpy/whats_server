# sse.py
import asyncio

connected_clients = []

async def push_to_clients(message: str):
    print("pushing to client")
    for queue in connected_clients:
        await queue.put(message)