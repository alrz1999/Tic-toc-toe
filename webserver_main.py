import asyncio
import logging
import enum
import uuid

import utils
from utils import async_input
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_GAMESERVER_REPO_PORT = 9090
WEBSERVER_CLIENT_REPO_PORT = 8989


class ChatRoom:
    def __init__(self, server_address: tuple):
        self.server_address = server_address
        self.room_id = str(uuid.uuid1())

    async def add_client(self, client_tcp_client: BaseTCPClient, start_message: BaseMessage = None):
        server_client = BaseTCPClient()
        await server_client.connect(self.server_address)
        await server_client.send(start_message)
        bridge = Bridge(server_client, client_tcp_client)
        task = None
        try:
            task = asyncio.create_task(bridge.run_full_duplex())
            await task
        except ClientConnectionException:
            raise
        finally:
            server_client.close()


class ChatroomRepository:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.all_chat_rooms: dict[str:ChatRoom] = dict()
        self.free_chat_rooms: dict[str:ChatRoom] = dict()
        self.free_multiplayer_chatrooms: dict[str:ChatRoom] = dict()
        self.waiting_chatrooms_by_username: dict[str: ChatRoom] = dict()

    def add_chatroom(self, chatroom: ChatRoom):
        self.free_chat_rooms[chatroom.room_id] = chatroom
        self.all_chat_rooms[chatroom.room_id] = chatroom

    def remove_chatroom(self, chatroom: ChatRoom):
        self.all_chat_rooms.pop(chatroom.room_id, None)
        self.remove_from_free_chatrooms(chatroom)
        self.remove_from_multiplayer_chatrooms(chatroom)
        self.remove_from_waiting_chatrooms(chatroom)

    def remove_from_waiting_chatrooms(self, chatroom):
        self.waiting_chatrooms_by_username = {k: v for k, v in self.waiting_chatrooms_by_username.items() if
                                              v != chatroom}

    def remove_from_multiplayer_chatrooms(self, chatroom):
        self.free_multiplayer_chatrooms.pop(chatroom.room_id, None)

    def remove_from_free_chatrooms(self, chatroom):
        self.free_chat_rooms.pop(chatroom.room_id, None)

    def pop_waiting_chatroom(self, username) -> ChatRoom | None:
        if username in self.waiting_chatrooms_by_username:
            print("popped from waiting sockets")
            return self.waiting_chatrooms_by_username.pop(username)
        return None

    async def pop_free_chatroom(self, single_player: bool) -> ChatRoom:
        while True:
            try:
                if single_player or len(self.free_multiplayer_chatrooms) == 0:
                    return self.free_chat_rooms.popitem()[1]
                else:
                    return self.free_multiplayer_chatrooms.popitem()[1]
            except KeyError:
                await asyncio.sleep(1)


class GameServerHandler:
    def __init__(self, tcp_client: BaseTCPClient, server_address: tuple, chatroom_repo: ChatroomRepository):
        self.tcp_client: BaseTCPClient = tcp_client
        self.server_address: tuple = server_address
        self.chatroom = ChatRoom(self.server_address)
        self.chatroom_repo = chatroom_repo
        self.chatroom_repo.add_chatroom(self.chatroom)

    async def handle_gameserver(self):
        # TODO add to list of available gameservers
        try:
            while True:
                message: BaseMessage = await self.tcp_client.receive()
                await self._handle_gameserver_message(message)
        except SocketClosedException:
            logger.info("A gameserver disconnected")
        finally:
            self.chatroom_repo.remove_chatroom(self.chatroom)
        # TODO remove from list of available gameservers

    async def _handle_gameserver_message(self, message: BaseMessage):
        json_content = message.content
        message_type = json_content['type']
        if message_type == "put_to_free":
            self.chatroom_repo.free_chat_rooms[self.chatroom.room_id] = self.chatroom
            self.chatroom_repo.remove_from_multiplayer_chatrooms(self.chatroom)
            self.chatroom_repo.remove_from_waiting_chatrooms(self.chatroom)
        elif message_type == "put_to_waiting":
            username = json_content['username']
            self.chatroom_repo.waiting_chatrooms_by_username[username] = self.chatroom
            self.chatroom_repo.remove_from_free_chatrooms(self.chatroom)
            self.chatroom_repo.remove_from_multiplayer_chatrooms(self.chatroom)
        elif message_type == "put_to_multi_free":
            self.chatroom_repo.free_multiplayer_chatrooms[self.chatroom.room_id] = self.chatroom
            self.chatroom_repo.remove_from_free_chatrooms(self.chatroom)
            self.chatroom_repo.remove_from_waiting_chatrooms(self.chatroom)
        else:
            logger.warning(f"unknown message type in gameserver handler: {message_type}")


class ServerConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class ClientConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class ChangeGameException(Exception):
    def __init__(self, message):
        super(ChangeGameException, self).__init__(message)


class Bridge:
    def __init__(self, server: BaseTCPClient, client: BaseTCPClient):
        self.server: BaseTCPClient = server
        self.client: BaseTCPClient = client
        self.quit = False

    async def run_full_duplex(self):
        tasks = [
            asyncio.create_task(self.forward_from_server_to_client()),
            asyncio.create_task(self.forward_from_client_to_server())
        ]
        try:
            await utils.wait_until_first_completed(tasks)
        except SocketClosedException:
            print('socket closed exception caught in Bridge.')
            raise

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


class ClientHandlerState(enum.Enum):
    CONNECTED = 0
    DISCONNECTED = 1


class ClientHandler:
    def __init__(self, tcp_client: BaseTCPClient, chatroom_repo: ChatroomRepository):
        self.tcp_client: BaseTCPClient = tcp_client
        self.chatroom_repo: ChatroomRepository = chatroom_repo
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
                        print("clientConnectionException")
                        break
                    except SocketClosedException:
                        print("unhandled socketClosedException in handle unmanaged Socket for client")
                else:
                    logger.debug("Unknown message content= ", json_content)
            except SocketClosedException:
                print("SocketClosedException at handle unmanaged socket")
                break
        self.state = ClientHandlerState.DISCONNECTED

    async def handle_game(self, tcp_client: BaseTCPClient, start_message: BaseMessage, is_single_player_game: bool):
        username = start_message.content['username']
        waiting_chatroom = self.chatroom_repo.pop_waiting_chatroom(username)
        chatroom: ChatRoom
        if waiting_chatroom:
            chatroom = waiting_chatroom
        else:
            try:
                tasks = [asyncio.create_task(x) for x in
                         [self.chatroom_repo.pop_free_chatroom(is_single_player_game),
                          self._handle_waiting_user_commands(tcp_client)]]
                chatroom = await utils.wait_until_first_completed(tasks)
            except ChangeGameException:
                return

        try:
            await chatroom.add_client(tcp_client, start_message)
            self.chatroom_repo.free_chat_rooms[chatroom.room_id] = chatroom
        except ServerConnectionException:
            self.chatroom_repo.remove_chatroom(chatroom)
            server_crashed_message = {
                "type": "server_crashed"
            }
            await tcp_client.send(BaseMessage(server_crashed_message))
        except ClientConnectionException:
            self.chatroom_repo.waiting_chatrooms_by_username[username] = chatroom
            raise


    async def _handle_waiting_user_commands(self, tcp_client: BaseTCPClient):
        while True:
            message = await tcp_client.receive()
            message_type = message.content["type"]
            if message_type == "change_game":
                raise ChangeGameException("change_game requested")


class ClientRepository:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.client_handlers = []

    def get_number_of_connected_clients(self):
        self.client_handlers = [x for x in self.client_handlers if x.state == ClientHandlerState.CONNECTED]
        return len(self.client_handlers)


class WebServer:
    def __init__(self, client_repo: ClientRepository, chatroom_repo: ChatroomRepository):
        self.client_repo: ClientRepository = client_repo
        self.chatroom_repo: ChatroomRepository = chatroom_repo

    async def accept_client(self):
        logger.info(
            f'start of SocketServer-accept with host={self.client_repo.tcp_server.host} and port={self.client_repo.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.client_repo.tcp_server.accept()
            logger.debug("A new user socket accepted.")
            client_socket_handler = ClientHandler(tcp_client, self.chatroom_repo)
            self.client_repo.client_handlers.append(client_socket_handler)
            self.client_repo.loop.create_task(client_socket_handler.handle_client(tcp_client))

    async def accept_gameserver(self):
        logger.info(
            f'start of SocketServer-accept with host={self.chatroom_repo.tcp_server.host} and port={self.chatroom_repo.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.chatroom_repo.tcp_server.accept()
            logger.info('A new GameServer socket accepted')
            handshake_message = await tcp_client.receive()
            server_address = (handshake_message.content["host"], handshake_message.content["port"])
            logger.info(f'The new GameServer is located at {server_address}')
            gameserver_handler = GameServerHandler(tcp_client, server_address, self.chatroom_repo)

            self.chatroom_repo.loop.create_task(gameserver_handler.handle_gameserver())


async def control_console(game_server_socket_server: ChatroomRepository,
                          clients_socket_server: ClientRepository):
    while True:
        print("WebServer Console".center(40, '*'))
        line = await async_input("available commands:\n/users\n/servers\n")
        if line == '/users':
            print("number of connected clients: ", clients_socket_server.get_number_of_connected_clients())
        elif line == '/servers':
            game_server_socket_server.all_chat_rooms = [x for x in
                                                        game_server_socket_server.all_chat_rooms if
                                                        x.state != "disconnected"]
            print("number of running servers: ", len(game_server_socket_server.all_chat_rooms))


async def start_webserver():
    logger.info('start of start_webserver')
    chatroom_repo = ChatroomRepository(WEBSERVER_HOST, WEBSERVER_GAMESERVER_REPO_PORT)
    client_repo = ClientRepository(WEBSERVER_HOST, WEBSERVER_CLIENT_REPO_PORT)
    web_server = WebServer(client_repo, chatroom_repo)
    await asyncio.gather(*[
        asyncio.create_task(web_server.accept_gameserver()),
        asyncio.create_task(web_server.accept_client()),
        asyncio.create_task(control_console(chatroom_repo, client_repo))
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
