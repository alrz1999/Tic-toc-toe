import asyncio
import logging

# XXX: REMOVE THIS LINE IN PRODUCTION!
import sys

from utils import json_decode, json_encode, async_input
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ServerSocketHandler:
    def __init__(self, socket, address):
        self.socket = socket
        self.host = address[0]
        self.port = address[1]
        self.states = ['unallocated', 'allocated', 'mid-allocated', 'disconnected', 'waiting']
        self.state = self.states[0]

    async def handle_unmanaged_socket(self, sock, address):
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

            json_content = json_decode(message.content, encoding='utf-8')
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

        tasks = [asyncio.create_task(bridge.run_full_duplex()) for bridge in bridges]
        # TODO Multiplayer
        await asyncio.gather(*tasks)


class GroupChatRoom:
    def __init__(self, host, port, server_socket_handler: ServerSocketHandler):
        self.host = host
        self.port = port
        self.server_socket_handler = server_socket_handler
        self.tasks = []

    async def add_client(self, client_tcp_client, start_message: BaseMessage = None):
        server_client = BaseTCPClient(self.host, self.port)
        await server_client.connect()
        await server_client.send(start_message)
        bridge = Bridge(server_client, client_tcp_client)
        task = asyncio.create_task(bridge.run_full_duplex())
        self.tasks.append(task)
        try:
            await task
        except ClientConnectionException:
            self.tasks.remove(task)
            raise


class GameServersSocketServer:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.all_sockets = []
        self.unallocated_sockets = []
        self.waiting_sockets_by_userid = dict()
        self.group_chat_rooms: list[GroupChatRoom] = []
        self.unallocated_group_chat_rooms: list[GroupChatRoom] = []
        self.waiting_chats_by_userid = dict()

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            sock, address = await self.tcp_server.accept()
            logger.info('game server sock accepted')
            server_tcp_client = BaseTCPClient("", 1, sock)
            message = await server_tcp_client.receive()
            json_content = json_decode(message.content, encoding='utf-8')
            server_socket_handler = ServerSocketHandler(sock, (json_content["host"], json_content["port"]))

            self.all_sockets.append(server_socket_handler)
            self.unallocated_sockets.append(server_socket_handler)

            self.loop.create_task(server_socket_handler.handle_unmanaged_socket(sock, address))

    def get_waiting_socket(self, username):
        if username in self.waiting_sockets_by_userid:
            print("poped from waiting sockets")
            return self.waiting_sockets_by_userid.pop(username)
        return None

    async def pop_unallocated_socket(self):
        while True:
            try:
                return self.unallocated_sockets.pop()
            except:
                await asyncio.sleep(1)

    def move_to_waiting(self, username, server_socket_handler: ServerSocketHandler):
        server_socket_handler.state = server_socket_handler.states[4]
        self.waiting_sockets_by_userid[username] = server_socket_handler
        self.loop.create_task(self._move_from_waiting_to_unallocated(username, server_socket_handler))

    def pop_unallocated_chat_room(self):
        try:
            return self.unallocated_group_chat_rooms.pop()
        except:
            return None

    async def _move_from_waiting_to_unallocated(self, username, server_socket_handler):
        print("_move_from_waiting_to_unallocated")
        await asyncio.sleep(5)
        print("after 10 second")
        print(self.waiting_sockets_by_userid.items())
        if username in self.waiting_sockets_by_userid:
            handler: ServerSocketHandler = self.waiting_sockets_by_userid.pop(username)
            if handler == server_socket_handler:
                abort_message = {
                    "type": "abort_game",
                    "username": username
                }

                tcp_server_client = BaseTCPClient(handler.host, handler.port,
                                                  handler.socket)
                await tcp_server_client.send(BaseMessage({}, json_encode(abort_message, encoding='utf-8')))
                self.unallocated_sockets.append(handler)
                handler.state = handler.states[0]

    def move_to_waiting_chat_rooms(self, username, chat_room: GroupChatRoom):
        self.waiting_chats_by_userid[username] = chat_room
        self.loop.create_task(self._move_chat_from_waiting_to_unallocated(username, chat_room))

    async def _move_chat_from_waiting_to_unallocated(self, username, chat_room: GroupChatRoom):
        print("_move_chat_from_waiting_to_unallocated")
        await asyncio.sleep(5)
        print("after 10 second")
        print(self.waiting_chats_by_userid.items())
        if username in self.waiting_chats_by_userid:
            chat: GroupChatRoom = self.waiting_chats_by_userid.pop(username)
            if chat == chat_room:
                abort_message = {
                    "type": "abort_game",
                    "username": username
                }
                for task in chat.tasks:
                    if not task.done():
                        task.cancel()
                handler = chat.server_socket_handler
                tcp_server_client = BaseTCPClient(handler.host, handler.port,
                                                  handler.socket)
                await tcp_server_client.send(BaseMessage({}, json_encode(abort_message, encoding='utf-8')))
                self.unallocated_sockets.append(handler)
                handler.state = handler.states[0]


class ClientSocketHandler:
    def __init__(self, socket, address, game_server_socket_server: GameServersSocketServer):
        self.socket = socket
        self.host = address[0]
        self.port = address[1]
        self.game_server_socket_server = game_server_socket_server
        self.states = ['connected', "disconnected"]
        self.state = self.states[1]

    async def handle_unmanaged_socket(self, sock, address):
        self.state = self.states[0]
        tcp_client = BaseTCPClient(address[0], address[1], sock)
        while True:
            try:
                message: BaseMessage = await tcp_client.receive()
                json_content = json_decode(message.content, 'utf-8')
                if json_content['type'] == 'start_game':
                    if json_content['game_type'] == "single":
                        try:
                            await self.handle_single_player_game(tcp_client, message)
                        except ClientConnectionException:
                            break
                        except SocketClosedException:
                            print("unhandled socketClosedException in handle unmanaged Socket for client")
                    elif json_content['game_type'] == "multi":
                        await self.handle_multi_player_game(tcp_client, message)
                else:
                    logger.debug("Unknown message content= ", json_content)
            except SocketClosedException:
                print("SocketClosedException at handle unmanaged socket")
                break
        self.state = self.states[1]

    def send(self, message):
        pass

    def receive(self):
        pass

    async def handle_single_player_game(self, tcp_client: BaseTCPClient, start_message: BaseMessage):
        while True:
            username = json_decode(start_message.content, 'utf-8')['username']
            waiting_socket = self.game_server_socket_server.get_waiting_socket(username)
            if waiting_socket:
                unallocated_server_socket = waiting_socket
            else:
                unallocated_server_socket: ServerSocketHandler = await self.game_server_socket_server.pop_unallocated_socket()

            tcp_server_client = BaseTCPClient(unallocated_server_socket.host, unallocated_server_socket.port,
                                              unallocated_server_socket.socket)

            unallocated_server_socket.state = unallocated_server_socket.states[1]

            try:
                if waiting_socket:
                    print("sending reconnect message")
                    reconnect_message = {
                        "type": "reconnect",
                        "username": username
                    }
                    await tcp_server_client.send(BaseMessage({}, json_encode(reconnect_message, encoding='utf-8')))
                else:
                    await tcp_server_client.send(start_message)
            except SocketClosedException:
                unallocated_server_socket.state = unallocated_server_socket.states[3]
                continue

            server_assigned_message = {
                "type": "server_assigned"
            }

            try:
                if not waiting_socket:
                    await tcp_client.send(BaseMessage({}, json_encode(server_assigned_message, encoding='utf-8')))
            except SocketClosedException:
                unallocated_server_socket.state = unallocated_server_socket.states[0]
                self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
                raise ClientConnectionException("error")

            chat_room = ChatRoom(unallocated_server_socket, [tcp_client], tcp_server_client)
            logger.debug('chatroom created')
            try:
                await chat_room.start()
            except ServerConnectionException:
                unallocated_server_socket.state = unallocated_server_socket.states[3]
                server_crashed_message = {
                    "type": "server_crashed"
                }

                await tcp_client.send(BaseMessage({}, json_encode(server_crashed_message, encoding="utf-8")))
                break
            except ClientConnectionException:
                self.game_server_socket_server.move_to_waiting(username, unallocated_server_socket)
                raise ClientConnectionException("error")

            unallocated_server_socket.state = unallocated_server_socket.states[0]
            self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
            break

    async def handle_multi_player_game(self, tcp_client: BaseTCPClient, start_message: BaseMessage):
        while True:
            username = json_decode(start_message.content, 'utf-8')['username']
            chat_room = self.game_server_socket_server.pop_unallocated_chat_room()
            if chat_room is None:
                unallocated_server_socket: ServerSocketHandler = await self.game_server_socket_server.pop_unallocated_socket()

                tcp_server_client = BaseTCPClient(unallocated_server_socket.host, unallocated_server_socket.port,
                                                  unallocated_server_socket.socket)

                unallocated_server_socket.state = unallocated_server_socket.states[2]

                try:
                    await tcp_server_client.send(start_message)
                except SocketClosedException:
                    unallocated_server_socket.state = unallocated_server_socket.states[3]
                    continue

                server_assigned_message = {
                    "type": "server_assigned",
                    "game_type": "multi"
                }

                try:
                    await tcp_client.send(BaseMessage({}, json_encode(server_assigned_message, encoding='utf-8')))
                except SocketClosedException:
                    unallocated_server_socket.state = unallocated_server_socket.states[0]
                    self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
                    raise ClientConnectionException("error")

                logger.debug("before creating chatroom")
                chat_room = GroupChatRoom(unallocated_server_socket.host, unallocated_server_socket.port, unallocated_server_socket)
                self.game_server_socket_server.unallocated_group_chat_rooms.append(chat_room)
                self.game_server_socket_server.group_chat_rooms.append(chat_room)
                logger.debug('Group chatroom created')
            try:
                await chat_room.add_client(tcp_client, start_message)
            except ServerConnectionException:
                server_socket_handler = chat_room.server_socket_handler
                server_socket_handler.state = server_socket_handler.states[3]
                server_crashed_message = {
                    "type": "server_crashed"
                }

                await tcp_client.send(BaseMessage({}, json_encode(server_crashed_message, encoding="utf-8")))
                break
            except ClientConnectionException:
                self.game_server_socket_server.move_to_waiting_chat_rooms(username, chat_room)
                raise ClientConnectionException("error")
            break

        if all(task.done() for task in chat_room.tasks):
            if chat_room.server_socket_handler not in self.game_server_socket_server.unallocated_sockets:
                self.game_server_socket_server.unallocated_sockets.append(chat_room.server_socket_handler)
                chat_room.server_socket_handler.state = chat_room.server_socket_handler.states[0]


class ClientsSocketServer:
    def __init__(self, host, port, game_server_socket_server: GameServersSocketServer):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.game_server_socket_server = game_server_socket_server
        self.loop = asyncio.get_event_loop()
        self.client_handlers = []

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            sock, address = await self.tcp_server.accept()
            logger.debug("client socket accepted")
            client_socket_handler = ClientSocketHandler(sock, address, self.game_server_socket_server)
            self.client_handlers.append(client_socket_handler)
            self.loop.create_task(client_socket_handler.handle_unmanaged_socket(sock, address))

    def get_number_of_connected_clients(self):
        self.client_handlers = [x for x in self.client_handlers if x.state != x.states[1]]
        return len(self.client_handlers)


class WebServer:
    def __init__(self, client_socket_server: ClientsSocketServer, game_server_socket_server: ClientsSocketServer):
        self.client_socket_server = client_socket_server
        self.game_server_socket_server = game_server_socket_server

    def handle_managed_sockets(self):
        pass

    def handle_unmanaged_sockets(self):
        pass


async def control_console(game_server_socket_server: GameServersSocketServer,
                          clients_socket_server: ClientsSocketServer):
    while True:
        print("WebServer Console".center(40, '*'))
        line = await async_input("available commands:\n/users\n/servers\n")
        if line == '/users':
            print("number of connected clients: ", clients_socket_server.get_number_of_connected_clients())
        elif line == '/servers':
            game_server_socket_server.all_sockets = [x for x in game_server_socket_server.all_sockets if
                                                     x.state != "disconnected"]
            print("number of running servers: ", len(game_server_socket_server.all_sockets))


async def start_webserver():
    # TODO: open socket and bind for accepting new clients and new servers
    logger.info('start of start_webserver')
    game_server_socket_server = GameServersSocketServer('127.0.0.1', 9090)
    clients_socket_server = ClientsSocketServer('127.0.0.1', 8989, game_server_socket_server)
    await asyncio.gather(*[
        asyncio.create_task(clients_socket_server.accept()),
        asyncio.create_task(game_server_socket_server.accept()),
        asyncio.create_task(control_console(game_server_socket_server, clients_socket_server))
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
