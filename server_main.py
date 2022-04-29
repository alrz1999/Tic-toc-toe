import asyncio
import random

from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage
from transport.tcp_server import BaseTCPServer
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


class MultiplayerController:
    def __init__(self):
        self.game = None
        self.client_by_username = dict()
        self.users = []
        self.loop = asyncio.get_event_loop()
        self.counter = 0

    async def async_handle_multiplayer(self, sock):
        tcp_client = BaseTCPClient("", 12, sock)
        start_message = await tcp_client.receive()
        json_content = json_decode(start_message.content, encoding='utf-8')
        username = json_content['username']
        self.client_by_username[username] = tcp_client
        if len(self.users) < 2:
            self.users.append(username)
        if len(self.users) == 2 and self.game is None:
            self.game = TicTocToe(self.users[0], self.users[1])
        has_new_change = True

        while True:
            if self.game is not None:
                await self.send_game_status(has_new_change)
                if self.game.has_game_finished():
                    break
            has_new_change = False

            message: BaseMessage = await tcp_client.receive()
            json_content = json_decode(message.content, encoding='utf-8')
            message_type = json_content['type']
            message_username = json_content['username']

            if message_type == 'place_mark':
                row, col = json_content['row'], json_content['col']
                try:
                    self.game.place_mark(message_username, row, col)
                    has_new_change = True
                    print("mark places")
                except Exception as rx:
                    print(rx)
            elif message_type == "abort_game":
                break
            elif message_type == "reconnect":
                has_new_change = True
            elif message_type == "chat":
                print("Start of Chat Message".center(40, "#"))
                print(json_content['text_message'])
                for key, val in self.client_by_username.items():
                    if key != username:
                        await val.send(message)
                print("End of Chat Message".center(40, "#"))

        self.client_by_username.pop(username)

    async def start_server(self):
        print("server socketserver started")
        tcp_server = BaseTCPServer(SERVER_HOST, SERVER_PORT)
        tasks = []
        while self.counter != 2:
            sock, address = await tcp_server.accept()
            task = self.loop.create_task(self.async_handle_multiplayer(sock))
            tasks.append(task)
            self.counter += 1

        print("try to close tcp server")
        print(tasks)
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if not task.done():
                task.cancel()
        print("try to close tcp server")
        tcp_server.close()
        print("server socketserver fully initialized")


    async def send_game_status(self, has_new_change):
        print("sending game status with ", has_new_change)
        game = self.game
        for username in self.users:
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
                await self.client_by_username[username].send(base_message)
                continue

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
                await self.client_by_username[username].send(base_message)


class ServerController:
    def __init__(self, tcp_client: BaseTCPClient, game_type: str):
        self.tcp_client: BaseTCPClient = tcp_client
        self.game_type = game_type
        print(f"ServerController initialized with game_type={game_type}")
        self.loop = asyncio.get_event_loop()

    async def handle_messages(self, starter_username):
        if self.game_type == 'single':
            await self.async_handle_single(starter_username)
        elif self.game_type == 'multi':
            multiplayer_controller = MultiplayerController()
            tasks = [asyncio.create_task(x) for x in [multiplayer_controller.start_server(),self.process_input()]]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            print(done)
            for task in tasks:
                if task is not done:
                    task.cancel()
        else:
            print("not known game type= ", self.game_type)

    async def process_input(self):
        print("in process_input")
        while True:
            message = await self.tcp_client.receive()
            print("message received")
            json_content = json_decode(message.content, encoding='utf-8')
            print(json_content)
            if json_content['type'] == 'change_game':
                return

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
            elif message_type == "chat":
                print("Start of Chat Message".center(40, "#"))
                print(json_content['text_message'])
                print("End of Chat Message".center(40, "#"))

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
            print("ready to get new clients.")
            message = await tcp_client.receive()
            json_content = json_decode(message.content, encoding='utf-8')
            if json_content['type'] == 'start_game':
                server_controller = ServerController(tcp_client, json_content['game_type'])
                await server_controller.handle_messages(json_content['username'])


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
