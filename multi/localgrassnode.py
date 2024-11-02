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

user_agent = UserAgent(os='windows', platforms='pc', browsers='chrome')
random_user_agent = user_agent.random

connected_users = {}
retry_attempts = {}

def display_connection_table():
    table = PrettyTable()
    table.field_names = ["No", "User ID", "Proxy", "Status", "Attempts"]
    for index, (user_id, info) in enumerate(connected_users.items(), start=1):
        attempts = retry_attempts.get(user_id, 0)
        table.add_row([index, user_id, info["proxy"], info["status"], attempts])
    logger.info("\n" + str(table))

async def monitor_connections():
    while True:
        display_connection_table()
        for user_id, info in connected_users.items():
            if info["status"] == "Disconnected":
                logger.info(f"[{user_id}] Attempting to reconnect...")
                asyncio.create_task(connect_to_wss(info["proxy"], user_id))
        await asyncio.sleep(3)

async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    retry_count = 0
    max_retries = 5  # Limit retries per connection attempt

    while True:  # Keep retrying until connected
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "User-Agent": random_user_agent,
                "Origin": "chrome-extension://lkbnfiajjmbhnfledhphioinpickokdi"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            urilist = ["wss://proxy.wynd.network:4444/", "wss://proxy.wynd.network:4650/"]
            uri = random.choice(urilist)
            server_hostname = "proxy.wynd.network"
            proxy = Proxy.from_url(socks5_proxy)

            async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                     extra_headers=custom_headers) as websocket:
                logger.info(f"[{user_id}] Connected to WebSocket: {uri} via {socks5_proxy}")
                connected_users[user_id] = {"proxy": socks5_proxy, "uri": uri, "status": "Connected"}
                retry_attempts[user_id] = 0  # Reset retry attempts on successful connection

                # Start ping task
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
                    break  # Exit loop to attempt reconnect
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        logger.warning(f"[{user_id}] Ping task was cancelled.")

                    connected_users[user_id]["status"] = "Disconnected"
                    display_connection_table()  # Update table immediately on disconnect

            # Increment retry count and delay
            retry_count += 1
            if retry_count >= max_retries:
                logger.warning(f"[{user_id}] Max retries reached, waiting before next attempt...")
                await asyncio.sleep(10)  # Longer wait after reaching max retries
            else:
                await asyncio.sleep(3 * retry_count)  # Exponential backoff
        except Exception as e:
            logger.error(f"[{user_id}] General connection error: {e}")
            connected_users[user_id] = {"proxy": socks5_proxy, "uri": uri, "status": "Failed"}
            retry_attempts[user_id] = retry_count
            display_connection_table()
            await asyncio.sleep(3 * retry_count)  # Exponential backoff

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
            await asyncio.sleep(60)
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
    proxy_count = len(local_proxies)
    user_count = len(user_ids)

    # Start the connection monitoring task
    monitor_task = asyncio.create_task(monitor_connections())
    tasks.append(monitor_task)

    for i in range(max(proxy_count, user_count)):
        user_id = user_ids[i % user_count]
        proxy = local_proxies[i % proxy_count]
        tasks.append(asyncio.ensure_future(connect_to_wss(proxy, user_id)))
        await asyncio.sleep(3)

    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
