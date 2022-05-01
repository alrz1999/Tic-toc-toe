import asyncio
import random
import logging
from asyncio import Task

import utils
import webserver_main
from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
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

    async def handle_client(self, tcp_client: BaseTCPClient, username: str):
        pass

    async def _handle_client_message(self, message: BaseMessage, username: str):
        json_content: dict = message.content
        message_type = json_content['type']
        message_username = json_content['username']

        if message_type == 'place_mark':
            row, col = json_content['row'], json_content['col']
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
            print(json_content['text_message'])
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
        self.has_new_change = True
        self.clients_by_username[username] = tcp_client

        while True:
            await self.send_game_status()
            if self.game.has_game_finished():
                break
            if self.try_place_computer_mark():
                continue
            message = await tcp_client.receive()
            await self._handle_client_message(message, username)

    def try_place_computer_mark(self):
        if self.game.get_game_userid("computer") != self.game.current_user:
            return False
        for i in range(3):
            for j in range(3):
                if self.game.board[i][j] == 0:
                    self.game.place_mark("computer", i, j)
                    self.has_new_change = True
                    return True


class MultiPlayerGame(Game):
    def __init__(self, user1: str):
        self.loop = asyncio.get_event_loop()
        self.user1 = user1
        self.user2 = None
        self.game = None
        self.clients_by_username: dict[str:BaseTCPClient] = dict()
        self.has_new_change = True
        self.abort_game = False

    async def handle_client(self, tcp_client: BaseTCPClient, username: str):
        self.has_new_change = True
        self.clients_by_username[username] = tcp_client

        if self.user2 is None:
            self.initialize_game(username)

        while True:
            await self.send_game_status()
            if self.game.has_game_finished():
                break
            message = await tcp_client.receive()
            await self._handle_client_message(message, username)

    def initialize_game(self, user2):
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
        self.single_player_game: SinglePlayerGame = None
        self.reconnect_task_by_username: dict[str:Task] = dict()

    async def start(self):
        while True:
            tcp_client = await self.tcp_server.accept()
            self.loop.create_task(self._handle_client(tcp_client))

    async def _handle_client(self, tcp_client: BaseTCPClient):
        # TODO: add to connected clients
        try:
            start_message: BaseMessage = await tcp_client.receive()
            start_content = start_message.content
            username = start_content['username']
            message_type = start_content['type']

            reconnect_task: Task = self.reconnect_task_by_username.pop(username, None)
            if reconnect_task is not None:
                reconnect_task.cancel()

            if message_type == 'start_game':
                game: Game = await self.get_game(tcp_client, username, start_content['game_type'])
                if game is not None:
                    try:
                        await game.handle_client(tcp_client, username)
                    except SocketClosedException:
                        try:
                            reconnect_task = asyncio.create_task(self._has_client_reconnected(game, username))
                            self.reconnect_task_by_username[username] = reconnect_task
                            reconnected: bool = await reconnect_task
                            if reconnected:
                                return
                            for user, client in game.clients_by_username.items():
                                opponent_disconnected_message = {
                                    "type": "opponent_escaped",
                                    "game_status": "finished"
                                }
                                await client.send(BaseMessage(opponent_disconnected_message))
                        except asyncio.exceptions.CancelledError:
                            return
                        except SocketClosedException:
                            pass

                free_message = {
                    "type": "put_to_free"
                }
                await self.master_client.send(BaseMessage(free_message))
                self.single_player_game = None
                self.multi_player_game = None
        finally:
            tcp_client.close()
        # TODO: remove from connected clients

    async def _has_client_reconnected(self, game, username) -> bool:
        if game.game.has_game_finished() or game.abort_game:
            return False

        wait_message = {
            "type": "put_to_waiting",
            "username": username
        }
        await self.master_client.send(BaseMessage(wait_message))
        reconnected = await self.wait_for_user_reconnect(game, username, 10)
        return reconnected

    async def get_game(self, tcp_client: BaseTCPClient, username: str, game_type: str) -> Game | None:
        if game_type == "single":
            return await self.get_single_player_game(username)
        return await self.get_multiplayer_game(tcp_client, username)

    async def get_single_player_game(self, username) -> SinglePlayerGame:
        if self.single_player_game is None:
            self.single_player_game = SinglePlayerGame(username)
        return self.single_player_game

    async def get_multiplayer_game(self, tcp_client: BaseTCPClient, username: str) -> MultiPlayerGame | None:
        if self.multi_player_game is None:
            self.multi_player_game = MultiPlayerGame(username)
            self.multi_player_game.clients_by_username[username] = tcp_client
            tasks = [asyncio.create_task(x) for x in
                     [self._check_multi_player_game_started(), self._handle_waiting_user_commands(tcp_client)]]
            try:
                multi_free_message = {
                    "type": "put_to_multi_free"
                }
                await self.master_client.send(BaseMessage(multi_free_message))
                server_assigned_message = {
                    "type": "server_assigned",
                    "game_type": "multi"
                }
                await tcp_client.send(BaseMessage(server_assigned_message))
                remain_in_game = await utils.wait_until_first_completed(tasks)
                if remain_in_game:
                    return self.multi_player_game

                changed_message = {
                    "type": "game_changed",
                    "game_status": "finished"
                }
                await tcp_client.send(BaseMessage(changed_message))
            except SocketClosedException:
                pass
            return None
        return self.multi_player_game

    async def _check_multi_player_game_started(self):
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

    async def wait_for_user_reconnect(self, game: Game, username: str, wait_time: int) -> bool:
        game.clients_by_username.pop(username)
        await asyncio.sleep(wait_time)
        return username in game.clients_by_username


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


def test_tic_toc_toe():
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
