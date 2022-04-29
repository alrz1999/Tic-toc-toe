import asyncio
import random

from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage
from utils import json_decode, json_encode

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_PORT = 9090

SERVER_HOST = '127.0.0.1'
SERVER_PORT = random.randint(10000, 50000)


async def async_handshake(tcp_client: BaseTCPClient):
    content = {
        "type": "handshake",
        "host": SERVER_HOST,
        "port": SERVER_PORT
    }
    message = BaseMessage({}, json_encode(content, encoding='utf-8'))
    await tcp_client.send(message)


class ServerController:
    def __init__(self, tcp_client: BaseTCPClient, game_type: str):
        self.tcp_client: BaseTCPClient = tcp_client
        self.game_type = game_type
        print(f"ServerController initialized with game_type={game_type}")

    async def handle_messages(self, starter_username):
        if self.game_type == 'single':
            await self.async_handle_single(starter_username)
        elif self.game_type == 'multi':
            await self.async_handle_multiplayer(starter_username)
        else:
            print("not known game type= ", self.game_type)

    async def async_handle_multiplayer(self, starter_username):
        print(f"handling multiplayer started with starter_username={starter_username}")
        second_username: str
        while True:
            message: BaseMessage = await self.tcp_client.receive()
            json_content = json_decode(message.content, 'utf-8')
            message_type = json_content['type']
            if message_type == 'multiplayer':
                second_username = json_content['username']
                break
            elif message_type == 'abort':
                return

        game: TicTocToe = TicTocToe(starter_username, second_username)

    async def async_handle_single(self, username):
        print(f"handling single player started with username={username}")
        has_new_change = True
        game: TicTocToe = TicTocToe(username, 'comp')

        while True:
            if game.has_game_finished():
                server_message = {
                    "type": "show_game_status",
                    "game_status": "finished",
                    "game_board": game.board,
                    "your_mark": game.get_game_userid(username),
                    "opponent_mark": game.get_game_opponent_userid(username),
                    "current_user": game.current_user,
                    "winner": game.winner
                }

                base_message = BaseMessage({}, json_encode(server_message, encoding='utf-8'))
                await self.tcp_client.send(base_message)
                break

            if has_new_change:
                server_message = {
                    "type": "show_game_status",
                    "game_status": "running",
                    "game_board": game.board,
                    "your_mark": game.get_game_userid(username),
                    "opponent_mark": game.get_game_opponent_userid(username),
                    "current_user": game.current_user
                }

                base_message = BaseMessage({}, json_encode(server_message, encoding='utf-8'))
                await self.tcp_client.send(base_message)

                has_new_change = False

            if game.get_game_userid('comp') == game.current_user:
                self.place_computer_mark(game)
                has_new_change = True
                continue

            message: BaseMessage = await self.tcp_client.receive()
            json_content = json_decode(message.content, encoding='utf-8')
            message_type = json_content['type']
            message_username = json_content['username']

            if message_type == 'place_mark':
                row, col = json_content['row'], json_content['col']
                try:
                    game.place_mark(message_username, row, col)
                    has_new_change = True
                except:
                    pass
            elif message_type == "abort_game":
                break
            elif message_type == "reconnect":
                has_new_change = True
                continue

    def place_computer_mark(self, game):
        for i in range(3):
            for j in range(3):
                if game.board[i][j] == 0:
                    game.place_mark('comp', i, j)
                    return


async def run_server():
    async with BaseTCPClient(WEBSERVER_HOST, WEBSERVER_PORT) as tcp_client:
        await async_handshake(tcp_client)
        while True:
            message = await tcp_client.receive()
            json_content = json_decode(message.content, encoding='utf-8')
            if json_content['type'] == 'start_game':
                server_controller = ServerController(tcp_client, json_content['game_type'])
                await server_controller.handle_messages(json_content['username'])
            # tcp_server = BaseTCPServer('127.0.0.1', 8787)
            # sock, address = await tcp_server.accept()
            # tcp_client = BaseTCPClient(address[0], address[1], sock)
            # server_controller = ServerController(tcp_client)
            # await server_controller.handle_messages()


if __name__ == '__main__':
    asyncio.run(run_server())
    a = 'a'
    b = 'b'
    tic = TicTocToe(a, b)
    tic.place_mark(a, 1, 0)
    tic.place_mark(b, 0, 2)
    tic.place_mark(a, 0, 0)
    tic.place_mark(b, 1, 1)
    tic.place_mark(a, 2, 2)
    print(tic.has_game_finished())
    tic.place_mark(b, 2, 0)
    print(tic.has_game_finished())
