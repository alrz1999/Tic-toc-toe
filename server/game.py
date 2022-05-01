import asyncio

from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage


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
