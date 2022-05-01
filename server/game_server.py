import asyncio
from asyncio import Task

import utils
from server.game import SinglePlayerGame, MultiPlayerGame, Game
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer


class GameServer:
    def __init__(self, master_client: BaseTCPClient, host, port):
        self.master_client = master_client
        self.tcp_server: BaseTCPServer = BaseTCPServer(host, port)
        self.loop = asyncio.get_event_loop()
        self.multi_player_game: MultiPlayerGame | None = None
        self.single_player_game: SinglePlayerGame | None = None
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
