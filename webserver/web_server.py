import asyncio
import logging

from transport.tcp_client import BaseTCPClient
from transport.tcp_server import BaseTCPServer
from webserver.chatroom import ChatroomRepository
from webserver.client_handler import ClientHandlerState, ClientHandler
from webserver.gameserver_handler import GameServerHandler

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
