import pprint

from client.game_client import GameClient
from client.game_controller import GameController


class MessageHandler:
    def __init__(self, game_client: GameClient, game_controller: GameController):
        self.game_controller = game_controller
        self.game_client = game_client

    async def handle_messages(self):
        self.game_controller.state = self.game_controller.states[0]
        while True:
            message = await self.game_client.receive()
            self.handle_message(message)

    def handle_message(self, message):
        message_type = message['type']

        if message_type == 'server_assigned':
            game_type = message.get("game_type")
            if game_type == 'multi':
                self.game_controller.state = self.game_controller.states[1]
            else:
                self.game_controller.state = self.game_controller.states[2]
        elif message_type == 'show_game_status':
            self.game_controller.state = self.game_controller.states[2]
            game_status = message['game_status']
            game_board = message['game_board']
            print("game_status = ", game_status)
            print("game_board : ")
            pprint.pprint(game_board, width=13)
            print('your mark = X')
            print('opponent mark = O')
            if game_status == 'finished':
                if message['winner'] == 0:
                    print("WITHDRAW".center(40, "*"))
                elif message['winner'] == message['your_mark']:
                    print("YOU WIN".center(40, "*"))
                else:
                    print("YOU LOSE".center(40, "*"))
                self.game_controller.state = self.game_controller.states[3]
            else:
                print('is your turn= ', message['current_user'] == message['your_mark'])
        elif message_type == 'server_crashed':
            print("Server crashed. Press Enter to return to Main menu")
            self.game_controller.state = self.game_controller.states[3]
        elif message_type == "chat":
            print("Start of Chat Message".center(40, "#"))
            print(message['text_message'])
            print("End of Chat Message".center(40, "#"))