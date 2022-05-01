import enum
import pprint
import re

from client.game_stub import GameStub
from utils import async_input


class ExitGameException(Exception):
    def __init__(self, message):
        super(ExitGameException, self).__init__(message)


class GameControllerState(enum.Enum):
    WAITING_FOR_SERVER = 0
    PLAYING = 1
    IDLE = 2
    WAITING_FOR_SECOND_USER = 3


class BaseGameController:
    def __init__(self, game_stub: GameStub):
        self.game_stub: GameStub = game_stub
        self.state = GameControllerState.IDLE

    async def handle_user_input(self):
        line = str.strip(await async_input("Enter your command\n"))
        await self._handle_user_command(line)

    async def _handle_user_command(self, command: str):
        if re.search(r'^(\d+ \d+)$', command) is not None:
            row, col = map(int, command.split())
            await self.game_stub.place_mark(row, col)
        elif command == 'cancel':
            await self.game_stub.cancel_game()
        elif command.startswith("chat:"):
            text_message = command.replace("chat:", '')
            await self.game_stub.send_message(text_message)
        elif command == '/exit':
            raise ExitGameException("exit")

    async def handle_interprocess_communications(self):
        while True:
            message = await self.game_stub.game_client.receive()
            self._handle_message(message)

    def _handle_message(self, message):
        message_type = message['type']

        if message_type == 'server_assigned':
            game_type = message.get("game_type")
            if game_type == 'multi':
                print(" A free server has been found ".center(40, "*"))
                self.state = GameControllerState.WAITING_FOR_SECOND_USER
            else:
                self.state = GameControllerState.PLAYING
        elif message_type == 'show_game_status':
            self.state = GameControllerState.PLAYING
            game_status = message['game_status']
            game_board = message['game_board']
            print("game_status = ", game_status)
            print("game_board : ")
            pprint.pprint(game_board, width=13)
            print(f'your mark = {message["your_mark"]}')
            op_mark = 1
            if op_mark == message["your_mark"]:
                op_mark = 2
            print(f'opponent mark = {op_mark}')
            if game_status == 'finished':
                if message['winner'] == 0:
                    print("WITHDRAW".center(40, "*"))
                elif message['winner'] == message['your_mark']:
                    print("YOU WIN".center(40, "*"))
                else:
                    print("YOU LOSE".center(40, "*"))
                self.state = GameControllerState.IDLE
            else:
                print('is your turn= ', message['current_user'] == message['your_mark'])
        elif message_type == 'server_crashed':
            print("Server crashed. Press Enter to return to Main menu")
            self.state = GameControllerState.IDLE
        elif message_type == "chat":
            print("Start of Chat Message".center(40, "#"))
            print(message['text_message'])
            print("End of Chat Message".center(40, "#"))
        elif message_type == "opponent_escaped":
            print(" Opponent has been disconnected ".center(40, "!"))
            print(" Press Enter to go Main Menu ".center(40, "*"))
            self.state = GameControllerState.IDLE


class SinglePlayerGameController(BaseGameController):
    def __init__(self, game_stub: GameStub):
        super().__init__(game_stub)

    async def handle_user_input(self):
        self.state = GameControllerState.WAITING_FOR_SERVER
        await self.game_stub.start_game("single")

        while self.state != GameControllerState.IDLE:
            print(" Single Player Menu ".center(40, "*"))
            if self.state == GameControllerState.WAITING_FOR_SERVER:
                print(" Waiting for a free server to start game... ".center(40, "#"))

            await super().handle_user_input()


class MultiPlayerGameController(BaseGameController):
    def __init__(self, game_stub: GameStub):
        super().__init__(game_stub)

    async def handle_user_input(self):
        self.state = GameControllerState.WAITING_FOR_SERVER
        await self.game_stub.start_game("multi")

        while self.state != GameControllerState.IDLE:
            print(" Multi Player Menu ".center(40, "*"))
            if self.state == GameControllerState.WAITING_FOR_SERVER:
                print(" Waiting for a free server to start game... ".center(40, "#"))
            elif self.state == GameControllerState.WAITING_FOR_SECOND_USER:
                print(" Waiting for second player... ".center(40, "#"))

            await super(MultiPlayerGameController, self).handle_user_input()

    async def _handle_user_command(self, command: str):
        await super(MultiPlayerGameController, self)._handle_user_command(command)
        if command == '/change':
            await self.game_stub.change_game()
            self.state = GameControllerState.IDLE
