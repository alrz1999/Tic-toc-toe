from client.game_client import GameClient


class GameStub:
    def __init__(self, game_client: GameClient):
        self.game_client: GameClient = game_client

    async def place_mark(self, row, col):
        message = {
            "type": "place_mark",
            "row": row,
            "col": col
        }

        await self.game_client.send(message)

    async def send_message(self, text_message):
        message = {
            "type": "chat",
            "text_message": text_message
        }

        await self.game_client.send(message)

    async def cancel_game(self):
        message = {
            "type": "cancel_game"
        }

        await self.game_client.send(message)

    async def start_game(self, game_type="single"):
        message = {
            "type": "start_game",
            "game_type": game_type
        }

        await self.game_client.send(message)
