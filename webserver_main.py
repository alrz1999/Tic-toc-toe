import asyncio
import logging

# XXX: REMOVE THIS LINE IN PRODUCTION!
import sys

from utils import json_decode, json_encode
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class HighLevelChatRoom:
    def __init__(self, server, client):
        # uses one exactly one socket from webserver to server
        pass


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
        while True:
            if self.quit:
                break
            message = await self.server.receive()
            await self.client.send(message)
            json_content = json_decode(message.content, encoding='utf-8')
            if json_content.get('game_status') == 'finished':
                self.quit = True
            # try:
            #     message = await self.server.receive()
            #     await self.client.send(message)
            #     json_content = json_decode(message.content, encoding='utf-8')
            #     if json_content.get('game_status') == 'finished':
            #         self.quit = True
            # except asyncio.exceptions.TimeoutError:
            #     print('timeout error in bridge. forward from server to client')

    async def forward_from_client_to_server(self):
        while True:
            if self.quit:
                break
            message = await self.client.receive()
            await self.server.send(message)
            # try:
            #     message = await asyncio.wait_for(self.client.receive(), 3)
            #     await self.server.send(message)
            # except asyncio.exceptions.TimeoutError:
            #     print('timeout error in bridge. forward from client to server')


class ChatRoom:
    def __init__(self, server, clients, server_tcp_client: BaseTCPClient = None):
        # uses one socket to server for each client so for 2 clients creates 2 socket to server
        # uses Bridge for dispatching message
        self.server_tcp_client = server_tcp_client
        self.server = server
        self.clients = clients

    async def start(self):
        bridges = []
        for client in self.clients:
            server_tcp_client = self.server_tcp_client
            if server_tcp_client is None:
                server_tcp_client = BaseTCPClient(self.server.host, self.server.port)
                await server_tcp_client.connect()
            bridge = Bridge(server_tcp_client, client)
            bridges.append(bridge)

        await asyncio.gather(*[bridge.run_full_duplex() for bridge in bridges])


class ServerSocketHandler:
    def __init__(self, socket, address):
        self.socket = socket
        self.host = address[0]
        self.port = address[1]
        self.states = ['unallocated', 'allocated', 'mid-allocated']
        self.state = self.states[0]

    async def handle_unmanaged_socket(self, sock, address):
        tcp_client = BaseTCPClient(address[0], address[1], sock)
        while True:
            if self.state != self.states[0]:
                await asyncio.sleep(1)
                continue

            print("blob")
            await asyncio.sleep(5)
            # try:
            #     message: BaseMessage = await asyncio.wait_for(tcp_client.receive(), 5)
            #     json_content = json_decode(message.content, 'utf-8')
            #     if json_content['type'] == 'start_single':
            #         pass
            #     elif json_content['type'] == 'start_multiplayer':
            #         pass
            #     else:
            #         logger.debug("Unknown message content= ", json_content)
            # except:
            #     print('waweil;a')
            #     pass

    def send(self, message):
        pass

    def receive(self):
        pass


class GameServersSocketServer:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.all_sockets = []
        self.unallocated_sockets = []

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            sock, address = await self.tcp_server.accept()
            logger.info('game server sock accepted')
            server_tcp_client = BaseTCPClient("", 1, sock)
            new_address = await server_tcp_client.receive()

            server_socket_handler = ServerSocketHandler(sock, address)

            self.all_sockets.append(server_socket_handler)
            self.unallocated_sockets.append(server_socket_handler)

            self.loop.create_task(server_socket_handler.handle_unmanaged_socket(sock, address))

    async def pop_unallocated_socket(self):
        while True:
            try:
                return self.unallocated_sockets.pop()
            except:
                await asyncio.sleep(1)


class ClientSocketHandler:
    def __init__(self, socket, address, game_server_socket_server: GameServersSocketServer):
        self.socket = socket
        self.host = address[0]
        self.port = address[1]
        self.game_server_socket_server = game_server_socket_server

    async def handle_unmanaged_socket(self, sock, address):
        tcp_client = BaseTCPClient(address[0], address[1], sock)
        while True:
            try:
                message: BaseMessage = await tcp_client.receive()
                json_content = json_decode(message.content, 'utf-8')
                if json_content['type'] == 'start_game':
                    unallocated_server_socket: ServerSocketHandler = await self.game_server_socket_server.pop_unallocated_socket()

                    tcp_server_client = BaseTCPClient(unallocated_server_socket.host, unallocated_server_socket.port,
                                                      unallocated_server_socket.socket)

                    unallocated_server_socket.state = unallocated_server_socket.states[1]
                    chat_room = ChatRoom(unallocated_server_socket, [tcp_client], tcp_server_client)
                    logger.debug('chatroom created')

                    try:
                        await tcp_server_client.send(message)
                    except SocketClosedException:
                        break

                    server_assigned_message = {
                        "type": "server_assigned"
                    }

                    try:
                        await tcp_client.send(BaseMessage({}, json_encode(server_assigned_message, encoding='utf-8')))
                    except SocketClosedException:
                        unallocated_server_socket.state = unallocated_server_socket.states[0]
                        self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
                        break
                    try:
                        await chat_room.start()
                    except:
                        print('chat room exception get')
                    unallocated_server_socket.state = unallocated_server_socket.states[0]
                    self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
                elif json_content['type'] == 'start_multiplayer':
                    pass
                else:
                    logger.debug("Unknown message content= ", json_content)
            except Exception as exception:
                pass
                # print(type(exception).__name__)
                # print(exception.__class__.__name__)

    def send(self, message):
        pass

    def receive(self):
        pass


class ClientsSocketServer:
    def __init__(self, host, port, game_server_socket_server: GameServersSocketServer):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.game_server_socket_server = game_server_socket_server
        self.loop = asyncio.get_event_loop()

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            sock, address = await self.tcp_server.accept()
            logger.debug("client socket accepted")
            client_socket_handler = ClientSocketHandler(sock, address, self.game_server_socket_server)
            self.loop.create_task(client_socket_handler.handle_unmanaged_socket(sock, address))


class WebServer:
    def __init__(self, client_socket_server: ClientsSocketServer, game_server_socket_server: ClientsSocketServer):
        self.client_socket_server = client_socket_server
        self.game_server_socket_server = game_server_socket_server

    def handle_managed_sockets(self):
        pass

    def handle_unmanaged_sockets(self):
        pass


async def start_webserver():
    # TODO: open socket and bind for accepting new clients and new servers
    logger.info('start of start_webserver')
    game_server_socket_server = GameServersSocketServer('127.0.0.1', 9090)
    clients_socket_server = ClientsSocketServer('127.0.0.1', 8989, game_server_socket_server)
    await asyncio.gather(*[
        asyncio.create_task(clients_socket_server.accept()),
        asyncio.create_task(game_server_socket_server.accept())
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
