import asyncio
import json
import random
import ssl
import uuid
import aiohttp
import os
import signal
from loguru import logger

# Daftar alternatif WSS URI
WSS_URIS = [
    "wss://proxy.wynd.network:4650/"
]

# Daftar User-Agent untuk Chrome dan Firefox di Windows
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

class WebSocketClient:
    def __init__(self):
        self.users = []
        self.current_uri_index = 0
        self.user_agents = {}
        self.log_folder = "logs"
        self.running = True  # Menandakan status client
        self.create_log_folder()

    def create_log_folder(self):
        if not os.path.exists(self.log_folder):
            os.makedirs(self.log_folder)
            logger.info(f"Log folder '{self.log_folder}' created.")

    def load_users_and_proxies(self):
        try:
            with open("users_proxies.json", "r") as file:
                data = json.load(file)
                return data.get("users", [])
        except FileNotFoundError:
            logger.error("users_proxies.json file not found!")
            return []

    def get_next_uri(self):
        uri = WSS_URIS[self.current_uri_index]
        self.current_uri_index = (self.current_uri_index + 1) % len(WSS_URIS)
        return uri

    async def heartbeat(self, websocket, user_id):
        while self.running:  # Cek status client
            try:
                await asyncio.sleep(20)
                heartbeat_msg = {
                    "action": "PING",
                    "id": str(uuid.uuid4())
                }
                await websocket.send_json(heartbeat_msg)
                logger.info(f"?? [{user_id}] Sent heartbeat")
            except Exception as e:
                logger.error(f"? [{user_id}] Heartbeat error: {str(e)}")
                break

    async def connect_to_wss(self, user_data):
        user_id = user_data['user_id']
        proxy = user_data['proxy']
        device_id = str(uuid.uuid4())

        logger.add(os.path.join(self.log_folder, f"{user_id}.log"), rotation="1 MB", retention="10 days", level="INFO", 
                   format="{time} {level} {message}\n===============================")

        if user_id not in self.user_agents:
            self.user_agents[user_id] = random.choice(USER_AGENTS)
        
        current_user_agent = self.user_agents[user_id]
        logger.info(f"User ID: {user_id} using User-Agent: {current_user_agent}")

        while self.running:  # Cek status client
            try:
                current_uri = self.get_next_uri()
                logger.info(f"Trying to connect to {current_uri}")

                await asyncio.sleep(random.uniform(0.1, 1.0))
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                connector = aiohttp.TCPConnector(ssl=ssl_context, force_close=True)
                
                logger.info(f"?? [{user_id}] Using proxy: {proxy}")
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.ws_connect(
                        current_uri,
                        headers={"User-Agent": current_user_agent},
                        proxy=proxy,
                        ssl=ssl_context,
                        heartbeat=30
                    ) as websocket:
                        logger.info(f"?? [{user_id}] Connected to WebSocket at {current_uri}")
                        
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
                                                "user_agent": current_user_agent,
                                                "timestamp": int(asyncio.get_event_loop().time()),
                                                "device_type": "extension",
                                                "version": "2.5.0"
                                            }
                                        }
                                        await websocket.send_json(auth_response)
                                        logger.info(f"?? [{user_id}] Sending AUTH response")
                                    
                                    elif data.get('action') == 'PING':
                                        ping_response = {
                                            "id": data['id'],
                                            "origin_action": "PONG"
                                        }
                                        await websocket.send_json(ping_response)
                                        logger.info(f"?? [{user_id}] Sending PONG response")
                                    
                                elif message.type == aiohttp.WSMsgType.CLOSED:
                                    logger.info(f"WebSocket closed for User ID {user_id}")
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

    async def main(self):
        users_and_proxies = self.load_users_and_proxies()
        tasks = [self.connect_to_wss(user_data) for user_data in users_and_proxies]
        await asyncio.gather(*tasks)

    def stop(self):
        self.running = False  # Mengubah status client menjadi tidak berjalan

async def shutdown(signum, loop):
    logger.info("Received exit signal, shutting down...")
    for task in asyncio.all_tasks(loop):
        task.cancel()
    await asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True)
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    client = WebSocketClient()

    # Menangani sinyal untuk menghentikan aplikasi
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, client.stop)

    try:
        loop.run_until_complete(client.main())
    finally:
        loop.close()
