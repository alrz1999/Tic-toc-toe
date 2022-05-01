import asyncio
import logging

from transport.tcp_client import BaseTCPClient
from transport.tcp_server import BaseTCPServer
from webserver.chatroom import ChatroomRepository
from webserver.client_handler import ClientHandlerState, ClientHandler
from webserver.gameserver_handler import GameServerHandler, GameServerHandlerState

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class GameServerRepository:
    def __init__(self, host, port, chatroom_repo: ChatroomRepository):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.chatroom_repo = chatroom_repo
        self.loop = asyncio.get_event_loop()
        self.gameserver_handlers = []

    async def accept_gameserver(self):
        logger.info(
            f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.tcp_server.accept()
            logger.info('A new GameServer socket accepted')
            handshake_message = await tcp_client.receive()
            server_address = (handshake_message.content["host"], handshake_message.content["port"])
            logger.info(f'The new GameServer is located at {server_address}')
            gameserver_handler = GameServerHandler(tcp_client, server_address, self.chatroom_repo)
            self.gameserver_handlers.append(gameserver_handler)
            self.loop.create_task(gameserver_handler.handle_gameserver())

    def get_number_of_connected_gameservers(self):
        self.gameserver_handlers = [x for x in self.gameserver_handlers if x.state == GameServerHandlerState.CONNECTED]
        return len(self.gameserver_handlers)


class ClientRepository:
    def __init__(self, host, port, chatroom_repo: ChatroomRepository):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.chatroom_repo = chatroom_repo
        self.loop = asyncio.get_event_loop()
        self.client_handlers = []

    async def accept_client(self):
        logger.info(
            f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.tcp_server.accept()
            logger.debug("A new user socket accepted.")
            client_socket_handler = ClientHandler(tcp_client, self.chatroom_repo)
            self.client_handlers.append(client_socket_handler)
            self.loop.create_task(client_socket_handler.handle_client(tcp_client))

    def get_number_of_connected_clients(self):
        self.client_handlers = [x for x in self.client_handlers if x.state == ClientHandlerState.CONNECTED]
        return len(self.client_handlers)
