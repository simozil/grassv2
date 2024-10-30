import asyncio
import random
import ssl
import json
import time
import uuid
import os
from rich.console import Console
from rich import print
from loguru import logger
import aiohttp

# Constants
VERSION = "2.5.0"
WSS_URI = "wss://proxy.wynd.network:4650/"
SERVER_HOSTNAME = "proxy.wynd.network"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

console = Console()

class GrassBot:
    def __init__(self):
        self.console = Console()

    def clear_terminal(self):
        os.system("cls" if os.name == "nt" else "clear")
        self.console.print("[bold magenta]BACTIAR 291 - Script Started![/bold magenta]", justify="center")
        self.console.print("[bold green]Welcome! Script will run shortly...[/bold green]\n", justify="center")

    @staticmethod
    def load_proxy():
        try:
            with open("proxy.json", "r") as file:
                proxy_data = json.load(file)
                return proxy_data.get("proxy_url")
        except FileNotFoundError:
            print("❌ [red]proxy.json file not found! Running without proxy.[/red]")
            return None

    @staticmethod
    def load_users():
        with open("users.json", "r") as file:
            users_data = json.load(file)
            return [user["user_id"] for user in users_data["users"]]

    async def send_ping(self, websocket, user_id):
        while True:
            try:
                ping_message = {
                    "id": str(uuid.uuid4()),
                    "version": "1.0.0",
                    "action": "PING",
                    "data": {}
                }
                print(f"📡 [blue][{user_id}][/blue] Sending PING")
                await websocket.send_str(json.dumps(ping_message))
                await asyncio.sleep(20)
            except Exception as e:
                print(f"❌ [red][{user_id}] Ping error: {e}[/red]")
                break

    async def handle_auth(self, websocket, message, device_id, user_id):
        try:
            auth_response = {
                "id": message["id"],
                "origin_action": "AUTH",
                "result": {
                    "browser_id": device_id,
                    "user_id": user_id,
                    "user_agent": USER_AGENT,
                    "timestamp": int(time.time()),
                    "device_type": "extension",
                    "version": VERSION
                }
            }
            print(f"🔐 [yellow][{user_id}] Sending AUTH response[/yellow]")
            await websocket.send_str(json.dumps(auth_response))
        except Exception as e:
            print(f"❌ [red][{user_id}] Auth error: {e}[/red]")

    async def handle_pong(self, websocket, message, user_id):
        try:
            pong_response = {
                "id": message["id"],
                "origin_action": "PONG"
            }
            print(f"🔄 [cyan][{user_id}] PONG received, responding...[/cyan]")
            await websocket.send_str(json.dumps(pong_response))
        except Exception as e:
            print(f"❌ [red][{user_id}] Pong error: {e}[/red]")

    async def connect_to_wss(self, user_id, proxy=None):
        device_id = str(uuid.uuid4())
        logger.info(f"Device ID: {device_id} for User ID: {user_id}")

        while True:
            try:
                await asyncio.sleep(random.uniform(0.1, 1.0))
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                connector = aiohttp.TCPConnector(ssl=ssl_context)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.ws_connect(
                        WSS_URI,
                        headers={"User-Agent": USER_AGENT},
                        proxy=proxy,
                        ssl=False
                    ) as websocket:
                        print(f"🌐 [green][{user_id}] Connected to WebSocket[/green]")
                        
                        # Start ping task
                        ping_task = asyncio.create_task(self.send_ping(websocket, user_id))

                        try:
                            async for msg in websocket:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    message = json.loads(msg.data)
                                    logger.info(f"Message received for User ID {user_id}: {message}")

                                    if "balance" in message.get("result", {}):
                                        balance = message["result"]["balance"]
                                        print(f"✅ [green][{user_id}] Balance updated: {balance}[/green]")

                                    if message.get("action") == "AUTH":
                                        await self.handle_auth(websocket, message, device_id, user_id)
                                    elif message.get("action") == "PONG":
                                        await self.handle_pong(websocket, message, user_id)
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    print(f"⚠️ [yellow][{user_id}] WebSocket connection closed[/yellow]")
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    print(f"❌ [red][{user_id}] WebSocket connection error[/red]")
                                    break

                        except Exception as e:
                            print(f"⚠️ [yellow][{user_id}] Connection error: {e}[/yellow]")
                        finally:
                            ping_task.cancel()

            except Exception as e:
                print(f"❌ [red][{user_id}] Connection error: {e}[/red]")
                await asyncio.sleep(5)

    async def run(self):
        self.clear_terminal()
        user_ids = self.load_users()
        proxy = self.load_proxy()
        
        if proxy:
            print(f"🌍 [green]Using proxy: {proxy}[/green]")
        
        tasks = [self.connect_to_wss(user_id, proxy) for user_id in user_ids]
        await asyncio.gather(*tasks)

def main():
    bot = GrassBot()
    asyncio.run(bot.run())

if __name__ == '__main__':
    main()
