import asyncio
import logging
import enum

from utils import async_input
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_GAMESERVER_REPO_PORT = 9090
WEBSERVER_CLIENT_REPO_PORT = 8989


class GameServerHandler:
    def __init__(self, tcp_client: BaseTCPClient, server_address: tuple):
        self.tcp_client: BaseTCPClient = tcp_client
        self.server_address: tuple = server_address
        self.chatroom = ChatRoom(self.server_address)
        self.states = ['unallocated', 'allocated', 'mid-allocated', 'disconnected', 'waiting']
        self.state = self.states[0]

    async def handle_unmanaged_socket(self, tcp_client: BaseTCPClient):
        pass
        # tcp_client = BaseTCPClient(address[0], address[1], sock)
        # while True:
        #     if self.state != self.states[0]:
        #         await asyncio.sleep(1)
        #         continue
        #     await asyncio.sleep(5)
        #     try:
        #         message: BaseMessage = await asyncio.wait_for(tcp_client.receive(), 5)
        #         json_content = json_decode(message.content, 'utf-8')
        #         if json_content['type'] == 'start_single':
        #             pass
        #         elif json_content['type'] == 'start_multiplayer':
        #             pass
        #         else:
        #             logger.debug("Unknown message content= ", json_content)
        #     except:
        #         print('waweil;a')
        #         pass


class ServerConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class ClientConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class Bridge:
    def __init__(self, server, client):
        self.server = server
        self.client = client
        self.quit = False

    async def run_full_duplex(self):
        tasks = [
            asyncio.create_task(self.forward_from_server_to_client()),
            asyncio.create_task(self.forward_from_client_to_server())
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            feature, = done
            feature.result()
        except SocketClosedException:
            print('socket closed exception caught in Bridge.')
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    print(f"task = {task.get_name()} cancelled.")

    async def forward_from_server_to_client(self):
        message: BaseMessage
        while True:
            if self.quit:
                break

            try:
                message = await self.server.receive()
            except SocketClosedException:
                raise ServerConnectionException("error")

            try:
                await self.client.send(message)
            except SocketClosedException:
                raise ClientConnectionException("error")

            json_content = message.content
            if json_content.get('game_status') == 'finished':
                self.quit = True

    async def forward_from_client_to_server(self):
        message: BaseMessage
        while True:
            if self.quit:
                break

            try:
                message = await self.client.receive()
            except SocketClosedException:
                raise ClientConnectionException("error")

            try:
                await self.server.send(message)
            except SocketClosedException:
                raise ServerConnectionException("error")


class ChatRoom:
    def __init__(self, server_address: tuple):
        self.server_address = server_address
        self.tasks = []
        self.counter = 0

    async def add_client(self, client_tcp_client: BaseTCPClient, start_message: BaseMessage = None):
        server_client = BaseTCPClient()
        await server_client.connect(self.server_address)
        await server_client.send(start_message)
        bridge = Bridge(server_client, client_tcp_client)
        self.counter += 1
        task = None
        try:
            task = asyncio.create_task(bridge.run_full_duplex())
            self.tasks.append(task)
            await task
        except ClientConnectionException:
            self.tasks.remove(task)
            raise

class GameServerRepository:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.all_gameserver_handlers: list[GameServerHandler] = []
        self.free_gameserver_handlers: list[GameServerHandler] = []
        self.free_multiplayer_gameserver_handler: list[GameServerHandler] = []
        self.waiting_gameserver_handlers_by_username: dict[str: GameServerHandler] = dict()

    def pop_waiting_gameserver_handler(self, username) -> GameServerHandler | None:
        if username in self.waiting_gameserver_handlers_by_username:
            print("poped from waiting sockets")
            return self.waiting_gameserver_handlers_by_username.pop(username)
        return None

    async def pop_free_gameserver_handler(self, single_player: bool) -> GameServerHandler:
        while True:
            try:
                if single_player:
                    return self.free_gameserver_handlers.pop()
                else:
                    return self.free_multiplayer_gameserver_handler.pop()
            except IndexError:
                await asyncio.sleep(1)

    def move_to_waiting(self, username, gameserver_handler: GameServerHandler):
        gameserver_handler.state = gameserver_handler.states[4]
        self.waiting_gameserver_handlers_by_username[username] = gameserver_handler
        self.loop.create_task(self._move_from_waiting_to_unallocated(username, gameserver_handler))

    async def _move_from_waiting_to_unallocated(self, username, gameserver_handler: GameServerHandler):
        print("_move_from_waiting_to_unallocated")
        await asyncio.sleep(5)
        print("after 10 second")
        print(self.waiting_gameserver_handlers_by_username.items())
        if username in self.waiting_gameserver_handlers_by_username:
            handler: GameServerHandler = self.waiting_gameserver_handlers_by_username.pop(username)
            if handler == gameserver_handler:
                abort_message = {
                    "type": "abort_game",
                    "username": username
                }

                tcp_server_client = handler.tcp_client
                await tcp_server_client.send(BaseMessage(abort_message))
                self.free_gameserver_handlers.append(handler)
                handler.state = handler.states[0]


class ClientHandlerState(enum.Enum):
    CONNECTED = 0
    DISCONNECTED = 1


class ClientHandler:
    def __init__(self, tcp_client: BaseTCPClient, gameserver_repo: GameServerRepository):
        self.tcp_client: BaseTCPClient = tcp_client
        self.gameserver_repo: GameServerRepository = gameserver_repo
        self.state = ClientHandlerState.DISCONNECTED

    async def handle_client(self, tcp_client: BaseTCPClient):
        self.state = ClientHandlerState.CONNECTED
        while True:
            try:
                message: BaseMessage = await tcp_client.receive()
                json_content = message.content
                if json_content['type'] == 'start_game':
                    try:
                        is_single_player_game = json_content['game_type'] == "single"
                        await self.handle_game(tcp_client, message, is_single_player_game)
                    except ClientConnectionException:
                        break
                    except SocketClosedException:
                        print("unhandled socketClosedException in handle unmanaged Socket for client")
                else:
                    logger.debug("Unknown message content= ", json_content)
            except SocketClosedException:
                print("SocketClosedException at handle unmanaged socket")
                break
        self.state = ClientHandlerState.DISCONNECTED

    async def handle_game(self, tcp_client: BaseTCPClient, start_message: BaseMessage, is_single_player_game:bool):
        while True:
            username = start_message.content['username']
            waiting_gameserver_handler = self.gameserver_repo.pop_waiting_gameserver_handler(username)
            gameserver_handler: GameServerHandler
            if waiting_gameserver_handler:
                gameserver_handler = waiting_gameserver_handler
            else:
                gameserver_handler = await self.gameserver_repo.pop_free_gameserver_handler(is_single_player_game)

            try:
                await gameserver_handler.chatroom.add_client(tcp_client, start_message)
            except ServerConnectionException:
                server_crashed_message = {
                    "type": "server_crashed"
                }

                await tcp_client.send(BaseMessage(server_crashed_message))
                break
            except ClientConnectionException:
                # self.gameserver_repo.move_to_waiting(username, gameserver_handler)
                raise ClientConnectionException("error")

            self.gameserver_repo.free_gameserver_handlers.append(gameserver_handler)
            break


class ClientRepository:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.client_handlers = []

    def get_number_of_connected_clients(self):
        self.client_handlers = [x for x in self.client_handlers if x.state != x.states[1]]
        return len(self.client_handlers)


class WebServer:
    def __init__(self, client_repo: ClientRepository, game_server_repo: GameServerRepository):
        self.client_repo: ClientRepository = client_repo
        self.game_server_repo: GameServerRepository = game_server_repo

    async def accept_client(self):
        logger.info(
            f'start of SocketServer-accept with host={self.client_repo.tcp_server.host} and port={self.client_repo.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.client_repo.tcp_server.accept()
            logger.debug("A new user socket accepted.")
            client_socket_handler = ClientHandler(tcp_client, self.game_server_repo)
            self.client_repo.client_handlers.append(client_socket_handler)
            self.client_repo.loop.create_task(client_socket_handler.handle_client(tcp_client))

    async def accept_gameserver(self):
        logger.info(
            f'start of SocketServer-accept with host={self.game_server_repo.tcp_server.host} and port={self.game_server_repo.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.game_server_repo.tcp_server.accept()
            logger.info('A new GameServer socket accepted')
            handshake_message = await tcp_client.receive()
            server_address = (handshake_message.content["host"], handshake_message.content["port"])
            logger.info(f'The new GameServer is located at {server_address}')
            server_socket_handler = GameServerHandler(tcp_client, server_address)

            self.game_server_repo.all_gameserver_handlers.append(server_socket_handler)
            self.game_server_repo.free_gameserver_handlers.append(server_socket_handler)

            self.game_server_repo.loop.create_task(server_socket_handler.handle_unmanaged_socket(tcp_client))


async def control_console(game_server_socket_server: GameServerRepository,
                          clients_socket_server: ClientRepository):
    while True:
        print("WebServer Console".center(40, '*'))
        line = await async_input("available commands:\n/users\n/servers\n")
        if line == '/users':
            print("number of connected clients: ", clients_socket_server.get_number_of_connected_clients())
        elif line == '/servers':
            game_server_socket_server.all_gameserver_handlers = [x for x in
                                                                 game_server_socket_server.all_gameserver_handlers if
                                                                 x.state != "disconnected"]
            print("number of running servers: ", len(game_server_socket_server.all_gameserver_handlers))


async def start_webserver():
    logger.info('start of start_webserver')
    game_server_repo = GameServerRepository(WEBSERVER_HOST, WEBSERVER_GAMESERVER_REPO_PORT)
    client_repo = ClientRepository(WEBSERVER_HOST, WEBSERVER_CLIENT_REPO_PORT)
    web_server = WebServer(client_repo, game_server_repo)
    await asyncio.gather(*[
        asyncio.create_task(web_server.accept_gameserver()),
        asyncio.create_task(web_server.accept_client()),
        asyncio.create_task(control_console(game_server_repo, client_repo))
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
