import asyncio
import logging
import re

from client.game_client import GameClient
from client.game_stub import GameStub
from transport.tcp_client import SocketClosedException
from utils import async_input


class GameController:
    def __init__(self, game_client: GameClient):
        self.game_stub: GameStub = GameStub(game_client)
        self.states = ['waiting for server', 'waiting for second user', 'playing', 'idle']
        self.state = self.states[0]

    async def async_control_main_menu(self):
        while True:
            command = await async_input("Main Menu\n1.Training\n2.Multiplayer\n3.Exit\n")
            command_lower = command.lower()
            try:
                if command_lower in {'1', 'train', 'training', '1.training'}:
                    await self.async_handle_training()
                elif command_lower in {'2', 'multi', 'multiplayer', '2.multiplayer'}:
                    await self.async_handle_multiplayer()
                elif command_lower in {'3', 'exit', '/exit', '3.exit'}:
                    return
                else:
                    logging.warning(f"Couldn't interpret your input: {command}")
            except SocketClosedException:
                self.state = self.states[3]
                print("Disconnected from webserver")

    async def async_handle_training(self):
        self.state = self.states[0]
        await self.game_stub.start_game("single")

        while self.state != self.states[3]:
            if self.state == self.states[0]:
                print("Training Menu\nWaiting for a free server to start game...\n")
            line = await async_input("Enter your command\n")

            if re.search(r'\d+ \d+', line) is not None:
                row, col = map(int, line.split())
                await self.game_stub.place_mark(row, col)
            elif line == 'cancel':
                await self.game_stub.cancel_game()
            elif len(line) == 0:
                continue
            elif line.startswith("chat:"):
                text_message = line.replace("chat:", '')
                await self.game_stub.send_message(text_message)
            else:
                print(f"not a valid message : {line}")
                # await self.game_stub.send_message(line)

    async def async_handle_multiplayer(self):
        self.state = self.states[0]
        await self.game_stub.start_game("multi")

        while self.state != self.states[3]:
            if self.state == self.states[0]:
                print("Waiting for a free server to start game...\n")
            if self.state == self.states[1]:
                print("Waiting for second player...\n")
            line = await async_input("Enter your command\n")

            if re.search(r'\d+ \d+', line) is not None:
                row, col = map(int, line.split())
                await self.game_stub.place_mark(row, col)
            elif line == 'cancel':
                await self.game_stub.cancel_game()
            else:
                await self.game_stub.send_message(line)
