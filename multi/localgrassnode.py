import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent

user_agent = UserAgent(os='windows', platforms='pc', browsers='chrome')
random_user_agent = user_agent.random

async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    logger.info(f"Device ID for {socks5_proxy}: {device_id}")

    while True:
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
                logger.info(f"Connected to WebSocket: {uri} via {socks5_proxy}")

                async def send_ping():
                    try:
                        while True:
                            send_message = json.dumps({
                                "id": str(uuid.uuid4()),
                                "version": "1.0.0",
                                "action": "PING",
                                "data": {}
                            })
                            logger.debug(f"Sending PING: {send_message}")
                            await websocket.send(send_message)
                            await asyncio.sleep(60)  # Increase ping interval
                    except asyncio.CancelledError:
                        logger.info("Ping task canceled.")
                    except Exception as e:
                        logger.error(f"Ping error: {e}")

                ping_task = asyncio.create_task(send_ping())

                try:
                    while True:
                        response = await websocket.recv()
                        message = json.loads(response)
                        logger.info(f"Received message: {message}")

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
                            logger.debug(f"Sending AUTH response: {auth_response}")
                            await websocket.send(json.dumps(auth_response))

                        elif message.get("action") == "PONG":
                            pong_response = {"id": message["id"], "origin_action": "PONG"}
                            logger.debug(f"Sending PONG response: {pong_response}")
                            await websocket.send(json.dumps(pong_response))

                except Exception as e:
                    logger.error(f"Connection error with {socks5_proxy}: {e}")
                finally:
                    ping_task.cancel()
                    await ping_task
                    logger.info(f"Reconnecting in 5 seconds for proxy {socks5_proxy}...")
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"General connection error: {e}")
            await asyncio.sleep(5)  # Delay before reconnecting

async def main():
    with open('user_id.txt', 'r') as user_file:
        user_ids = user_file.read().splitlines()

    print(f"Jumlah akun: {len(user_ids)}")

    with open('local_proxies.txt', 'r') as proxy_file:
        local_proxies = proxy_file.read().splitlines()

    tasks = []
    proxy_count = len(local_proxies)
    user_count = len(user_ids)

    for i in range(max(proxy_count, user_count)):
        user_id = user_ids[i % user_count]
        proxy = local_proxies[i % proxy_count]
        tasks.append(asyncio.ensure_future(connect_to_wss(proxy, user_id)))
        await asyncio.sleep(0.5)  # Brief delay to prevent rapid simultaneous connections

    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
