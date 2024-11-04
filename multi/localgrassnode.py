import asyncio
import random
import ssl
import json
import time
import uuid
import os
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent
from prettytable import PrettyTable
import itertools

user_agent = UserAgent(os='windows', platforms='pc', browsers='chrome')
random_user_agent = user_agent.random

connected_users = {}
failed_connections = {}
retry_attempts = {}
user_ip_count = {}  # Menyimpan jumlah IP yang digunakan oleh setiap user ID

def display_connection_table():
    table = PrettyTable()
    table.field_names = ["No", "User ID", "Proxy", "Status", "IP Count"]  # Kolom Attempts dihapus
    for index, (user_id, info) in enumerate(connected_users.items(), start=1):
        ip_count = user_ip_count.get(user_id, 0)
        table.add_row([index, user_id, info["proxy"], info["status"], ip_count])  # Kolom Attempts dihapus
    logger.info("\n" + str(table))

async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    logger.info(f"Device ID for {socks5_proxy}: {device_id}")

    retry_count = 0
    max_retries = 5  # Maximum number of retries
    backoff_time = 1  # Start with 1 second backoff

    urilist_secure = ["wss://proxy.wynd.network:4650/"]
    urilist_non_secure = ["ws://proxy.wynd.network:4650/"]

    while retry_count < max_retries:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "User-Agent": random_user_agent,
                "Origin": "chrome-extension://lkbnfiajjmbhnfledhphioinpickokdi"
            }
            
            use_secure = random.choice([True, False])
            uri = random.choice(urilist_secure if use_secure else urilist_non_secure)
            server_hostname = "proxy.wynd.network"
            proxy = Proxy.from_url(socks5_proxy)

            ssl_context = None
            if use_secure:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                     extra_headers=custom_headers) as websocket:
                logger.info(f"Connected to WebSocket: {uri} via {socks5_proxy}")

                connected_users[user_id] = {"proxy": socks5_proxy, "uri": uri, "status": "Connected"}
                if user_id in failed_connections:
                    failed_connections.pop(user_id, None)
                retry_attempts[user_id] = 0  # Reset retry count
                
                # Tambah jumlah IP untuk user_id
                if user_id not in user_ip_count:
                    user_ip_count[user_id] = 0
                user_ip_count[user_id] += 1

                await asyncio.sleep(3)  # Delay before displaying the table
                display_connection_table()

                ping_task = asyncio.create_task(send_ping(websocket, user_id))

                try:
                    while True:
                        response = await websocket.recv()
                        message = json.loads(response)
                        logger.info(f"[{user_id}] Received message: {message}")

                        if message.get("action") == "AUTH":
                            auth_response = {
                                "id": message["id"],
                                "origin_action": "AUTH",
                                "result": {
                                    "browser_id": device_id,
                                    "user_id": user_id,
                                    "user_agent": custom_headers['User-Agent'],
                                    "timestamp": int(time.time()),
                                    "device_type": "extension",
                                    "version": "4.26.2",
                                    "extension_id": "lkbnfiajjmbhnfledhphioinpickokdi"
                                }
                            }
                            logger.debug(f"[{user_id}] Sending AUTH response: {auth_response}")
                            await websocket.send(json.dumps(auth_response))

                        elif message.get("action") == "PONG":
                            pong_response = {"id": message["id"], "origin_action": "PONG"}
                            logger.debug(f"[{user_id}] Sending PONG response: {pong_response}")
                            await websocket.send(json.dumps(pong_response))

                except Exception as e:
                    logger.error(f"[{user_id}] Connection error with {socks5_proxy}: {e}")
                    break
                finally:
                    await asyncio.sleep(3)
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        logger.warning(f"[{user_id}] Ping task was cancelled.")

                    connected_users[user_id]["status"] = "Disconnected"
                    await asyncio.sleep(3)
                    display_connection_table()
                    logger.warning(f"[{user_id}] Connection closed, retrying in {backoff_time} seconds...")
                    await asyncio.sleep(backoff_time)

            retry_count += 1
            backoff_time *= 2

        except Exception as e:
            logger.error(f"[{user_id}] General connection error: {e}")
            if user_id not in failed_connections:
                failed_connections[user_id] = {"proxy": socks5_proxy, "uri": uri, "attempts": retry_count}
            connected_users[user_id] = {"proxy": socks5_proxy, "uri": uri, "status": "Failed"}
            await asyncio.sleep(1)
            display_connection_table()
            await asyncio.sleep(backoff_time)

async def send_ping(websocket, user_id):
    while True:
        try:
            send_message = json.dumps({
                "id": str(uuid.uuid4()),
                "version": "1.0.0",
                "action": "PING",
                "data": {}
            })
            logger.debug(f"[{user_id}] Sending PING: {send_message}")
            await websocket.send(send_message)
            await asyncio.sleep(60)  # Delay of 60 seconds before the next ping
        except Exception as e:
            logger.error(f"[{user_id}] Error sending PING: {e}")
            break

async def main():
    with open('user_id.txt', 'r') as user_file:
        user_ids = user_file.read().splitlines()

    print(f"Jumlah akun: {len(user_ids)}")

    with open('local_proxies.txt', 'r') as proxy_file:
        local_proxies = proxy_file.read().splitlines()

    tasks = []
    for user_id, proxy in itertools.product(user_ids, local_proxies):
        tasks.append(asyncio.ensure_future(connect_to_wss(proxy, user_id)))
        await asyncio.sleep(3)  # Slight delay between task starts

    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
