import asyncio

from client.game_client import GameClient
from client.game_controller import GameController
from client.server_message_handler import MessageHandler
from transport.tcp_client import BaseTCPClient
from utils import async_input

HOST = '127.0.0.1'
PORT = 8989


async def async_get_username() -> str:
    return await async_input("Welcome!\nEnter you username:\n")


async def start_client():
    username = await async_get_username()

    while True:
        tcp_client = BaseTCPClient(HOST, PORT)

        try:
            await tcp_client.connect()

        except ConnectionRefusedError:
            for timeout in [1, 3, 10]:
                try:
                    print(f"Can not connect to webserver. Trying to reconnect after {timeout}s.")
                    await asyncio.sleep(timeout)
                    await tcp_client.connect()
                    break
                except ConnectionRefusedError:
                    pass
            else:
                print("Webserver is not available. Try another time.")
                break

        game_client = GameClient(username, tcp_client)
        game_controller = GameController(game_client)
        message_handler = MessageHandler(game_client, game_controller)
        tasks = [asyncio.create_task(game_controller.async_control_main_menu()),
                 asyncio.create_task(message_handler.handle_messages())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            feature, = done
            feature.result()
            break
        except ConnectionResetError:
            continue
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    print(f"task = {task.get_name()} cancelled.")


if __name__ == '__main__':
    try:
        asyncio.run(start_client())
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass

