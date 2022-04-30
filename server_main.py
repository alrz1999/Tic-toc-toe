import asyncio
import random
import logging

import utils
import webserver_main
from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = webserver_main.WEBSERVER_HOST
WEBSERVER_PORT = webserver_main.WEBSERVER_GAMESERVER_REPO_PORT
WEBSERVER_ADDRESS = (WEBSERVER_HOST, WEBSERVER_PORT)

SERVER_HOST = '127.0.0.1'
SERVER_PORT = random.randint(10000, 50000)
SERVER_ADDRESS = (SERVER_HOST, SERVER_PORT)


async def async_handshake(tcp_client: BaseTCPClient):
    content = {
        "type": "handshake",
        "host": SERVER_HOST,
        "port": SERVER_PORT
    }

    await tcp_client.send(BaseMessage(content))


class Game:
    def __init__(self, user1: str, user2: str):
        self.user1 = user1
        self.user2 = user2
        self.game = TicTocToe(user1, user2)
        self.clients_by_username: dict[str:BaseTCPClient] = dict()
        self.has_new_change = True
        self.abort_game = False

    async def _handle_client_message(self, message: dict, username: str):
        message_type = message['type']
        message_username = message['username']

        if message_type == 'place_mark':
            row, col = message['row'], message['col']
            try:
                self.game.place_mark(message_username, row, col)
                self.has_new_change = True
            except:
                pass
        elif message_type == "abort_game":
            self.abort_game = True
            # TODO Send message to users
        elif message_type == "reconnect":
            self.has_new_change = True
        elif message_type == "chat":
            print("Start of Chat Message".center(40, "#"))
            print(message['text_message'])
            for key, val in self.clients_by_username.items():
                if key != username:
                    await val.send(message)
            print("End of Chat Message".center(40, "#"))

    async def send_game_status(self):
        print("sending game status with ", self.has_new_change)
        has_new_change = self.has_new_change
        self.has_new_change = False
        game = self.game

        for username, tcp_client in self.clients_by_username.items():
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

                await tcp_client.send(BaseMessage(server_message))
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

                base_message = BaseMessage(server_message)
                await tcp_client.send(base_message)


class SinglePlayerGame(Game):
    def __init__(self, username: str):
        super(SinglePlayerGame, self).__init__(username, "computer")
        self.loop = asyncio.get_event_loop()

    async def handle_client(self, tcp_client: BaseTCPClient, username: str):
        self.clients_by_username[username] = tcp_client

        while True:
            await self.send_game_status()
            if self.game.has_game_finished():
                break
            if self.try_place_computer_mark():
                continue
            message = await tcp_client.receive()
            await self._handle_client_message(message.content, username)

    def try_place_computer_mark(self):
        if self.game.get_game_userid("computer") != self.game.current_user:
            return False
        for i in range(3):
            for j in range(3):
                if self.game.board[i][j] == 0:
                    self.game.place_mark("computer", i, j)
                    return


class MultiPlayerGame(Game):
    def __init__(self, user1: str):
        self.loop = asyncio.get_event_loop()
        self.user1 = user1
        self.user2 = None
        # self.game = TicTocToe(user1, user2)
        self.clients_by_username: dict[str:BaseTCPClient] = dict()
        self.has_new_change = True
        self.abort_game = False

    async def handle_client(self, tcp_client: BaseTCPClient, username: str):
        self.clients_by_username[username] = tcp_client

        while True:
            await self.send_game_status()
            if self.game.has_game_finished():
                break
            message = await tcp_client.receive()
            await self._handle_client_message(message.content, username)

    def set_second_user(self, user2):
        self.user2 = user2
        self.game = TicTocToe(self.user1, self.user2)
        self.has_new_change = True
        self.abort_game = False


class GameServer:
    def __init__(self, master_client: BaseTCPClient, host, port):
        self.master_client = master_client
        self.tcp_server: BaseTCPServer = BaseTCPServer(host, port)
        self.loop = asyncio.get_event_loop()
        self.multi_player_game: MultiPlayerGame = None

    async def start(self):
        while True:
            tcp_client = await self.tcp_server.accept()
            self.loop.create_task(self._handle_client(tcp_client))

    async def _handle_client(self, tcp_client: BaseTCPClient):
        # TODO: add to connected clients
        while True:
            message: BaseMessage = await tcp_client.receive()
            json_content = message.content
            username = json_content['username']

            if json_content['type'] == 'start_game':
                if json_content['game_type'] == "single":
                    single_player_game = SinglePlayerGame(username)
                    await single_player_game.handle_client(tcp_client, username)
                elif json_content['game_type'] == "multi":
                    if self.multi_player_game is None:
                        self.multi_player_game = MultiPlayerGame(username)
                        tasks = [asyncio.create_task(x) for x in
                                 [self._check_multi_player_game(), self._handle_waiting_user_commands(tcp_client)]]
                        try:
                            result = await utils.wait_until_first_completed(tasks)
                            if not result:
                                await self.cancel_multi_player_game()
                                break
                        except:
                            await self.cancel_multi_player_game()
                            break
                    else:
                        self.multi_player_game.set_second_user(username)
                        await self.multi_player_game.handle_client(tcp_client, username)
                else:
                    break

        # TODO: remove from connected clients

    async def cancel_multi_player_game(self):
        self.multi_player_game = None
        cancel_multi_player_message = {
            "type": "cancel_game",
            "game_type": "multi"
        }
        await self.master_client.send(BaseMessage(cancel_multi_player_message))

    async def _check_multi_player_game(self):
        while True:
            if self.multi_player_game.game is not None:
                return True
            await asyncio.sleep(1)

    async def _handle_waiting_user_commands(self, tcp_client: BaseTCPClient):
        while True:
            message = await tcp_client.receive()
            message_type = message.content["type"]
            if message_type == "change_game":
                return False


async def run_server():
    master_client = BaseTCPClient()
    await master_client.connect(WEBSERVER_ADDRESS)
    await async_handshake(master_client)
    game_server = GameServer(master_client, SERVER_HOST, SERVER_PORT)
    try:
        await game_server.start()
    finally:
        game_server.tcp_server.close()
        master_client.close()

if __name__ == '__main__':
    asyncio.run(run_server())


def test_game():
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
