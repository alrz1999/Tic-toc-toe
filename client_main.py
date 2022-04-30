import asyncio

import webserver_main
from client.game_client import GameClient
from client.game_controller import MultiPlayerGameController, SinglePlayerGameController, \
    BaseGameController, ExitGameException
from client.game_stub import GameStub
from transport.tcp_client import BaseTCPClient, SocketClosedException
from utils import async_input, wait_until_first_completed

WEBSERVER_HOST = webserver_main.WEBSERVER_HOST
WEBSERVER_PORT = webserver_main.WEBSERVER_CLIENT_SERVER_PORT
WEBSERVER_ADDRESS = (WEBSERVER_HOST, WEBSERVER_PORT)


async def async_get_username() -> str:
    return await async_input("Welcome!\nEnter you username:\n")


async def async_control_main_menu(game_stub: GameStub) -> BaseGameController | None:
    while True:
        print(" Main Menu ".center(40, "*"))
        command = await async_input("1.Training\n2.Multiplayer\n3.Exit\n")
        command_lower = str.strip(command.lower())
        try:
            if command_lower in {'1', 'train', 'training', '1.training'}:
                return SinglePlayerGameController(game_stub)
            elif command_lower in {'2', 'multi', 'multiplayer', '2.multiplayer'}:
                return MultiPlayerGameController(game_stub)
            elif command_lower in {'3', 'exit', '/exit', '3.exit'}:
                raise ExitGameException("exit")
        except SocketClosedException:
            print("Disconnected from webserver")


async def start_client():
    username = await async_get_username()

    tcp_client = BaseTCPClient()
    game_client = GameClient(username, tcp_client)
    game_stub = GameStub(game_client)

    try:
        await tcp_client.connect_with_timeout(WEBSERVER_ADDRESS, [1, 3, 10])
    except ConnectionRefusedError:
        print("Webserver is not available. Try another time.")
        return

    while True:
        try:
            game_controller = await async_control_main_menu(game_stub)
            tasks = [asyncio.create_task(x) for x in
                     [game_controller.handle_user_input(), game_controller.handle_interprocess_communications()]]
            await wait_until_first_completed(tasks)
        except ConnectionResetError:
            raise
        except ExitGameException:
            return


if __name__ == '__main__':
    try:
        asyncio.run(start_client())
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
