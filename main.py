import asyncio
import json
import random
import ssl
import uuid
import aiohttp
from loguru import logger

WSS_URI = "wss://proxy.wynd.network:4650/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

class WebSocketClient:
    def __init__(self):
        self.users = []

    def clear_terminal(self):
        print("\033[H\033[J", end="")

    def load_users_and_proxies(self):
        try:
            with open("users_proxies.json", "r") as file:
                data = json.load(file)
                return data.get("users", [])
        except FileNotFoundError:
            logger.error("users_proxies.json file not found!")
            return []

    async def heartbeat(self, websocket, user_id):
        while True:
            try:
                await asyncio.sleep(20)  # Send heartbeat every 20 seconds
                heartbeat_msg = {
                    "action": "PING",
                    "id": str(uuid.uuid4())
                }
                await websocket.send_json(heartbeat_msg)
                logger.info(f"❤️ [{user_id}] Sent heartbeat")
            except Exception as e:
                logger.error(f"❌ [{user_id}] Heartbeat error: {str(e)}")
                break

    async def connect_to_wss(self, user_data):
        user_id = user_data['user_id']
        proxy = user_data['proxy']
        device_id = str(uuid.uuid4())
        logger.info(f"Device ID: {device_id} for User ID: {user_id}")

        while True:
            try:
                await asyncio.sleep(random.uniform(0.1, 1.0))
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                connector = aiohttp.TCPConnector(ssl=ssl_context, force_close=True)
                
                logger.info(f"🌐 [{user_id}] Using proxy: {proxy}")
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.ws_connect(
                        WSS_URI,
                        headers={"User-Agent": USER_AGENT},
                        proxy=proxy,
                        ssl=False,
                        heartbeat=30  # Enable built-in heartbeat
                    ) as websocket:
                        logger.info(f"🌐 [{user_id}] Connected to WebSocket")
                        
                        # Start heartbeat task
                        heartbeat_task = asyncio.create_task(self.heartbeat(websocket, user_id))
                        
                        try:
                            async for message in websocket:
                                if message.type == aiohttp.WSMsgType.TEXT:
                                    data = json.loads(message.data)
                                    logger.info(f"Message received for User ID {user_id}: {data}")
                                    
                                    if data.get('action') == 'AUTH':
                                        auth_response = {
                                            "id": data['id'],
                                            "origin_action": "AUTH",
                                            "result": {
                                                "browser_id": device_id,
                                                "user_id": user_id,
                                                "user_agent": USER_AGENT,
                                                "timestamp": int(asyncio.get_event_loop().time()),
                                                "device_type": "extension",
                                                "version": "2.5.0"
                                            }
                                        }
                                        await websocket.send_json(auth_response)
                                        logger.info(f"🔐 [{user_id}] Sending AUTH response")
                                    
                                    elif data.get('action') == 'PING':
                                        ping_response = {
                                            "id": data['id'],
                                            "origin_action": "PONG"
                                        }
                                        await websocket.send_json(ping_response)
                                        logger.info(f"📡 [{user_id}] Sending PONG response")
                                    
                                elif message.type == aiohttp.WSMsgType.CLOSED:
                                    logger.warning(f"WebSocket closed for User ID {user_id}")
                                    break
                                elif message.type == aiohttp.WSMsgType.ERROR:
                                    logger.error(f"WebSocket error for User ID {user_id}")
                                    break
                        except Exception as e:
                            logger.error(f"Error in WebSocket loop for User ID {user_id}: {str(e)}")
                        finally:
                            heartbeat_task.cancel()

            except aiohttp.ClientConnectorError as e:
                logger.error(f"Connection error for User ID {user_id}: {str(e)}")
            except aiohttp.ClientProxyConnectionError as e:
                logger.error(f"Proxy connection error for User ID {user_id}: {str(e)}")
            except Exception as e:
                logger.error(f"Error for User ID {user_id}: {str(e)}")
            
            logger.info(f"Reconnecting for User ID {user_id} in 5 seconds...")
            await asyncio.sleep(5)  # Wait before reconnecting

    async def run(self):
        self.clear_terminal()
        users_data = self.load_users_and_proxies()
        
        if users_data:
            logger.info(f"🌍 Loaded {len(users_data)} user-proxy pairs")
        else:
            logger.warning("⚠️ No user-proxy pairs loaded. Exiting.")
            return

        tasks = [self.connect_to_wss(user_data) for user_data in users_data]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    client = WebSocketClient()
    asyncio.run(client.run())
