import asyncio
import logging

from utils import async_input
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from transport.tcp_server import BaseTCPServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_GAME_SERVER_PORT = 9090
WEBSERVER_CLIENT_SERVER_PORT = 8989


class ServerSocketHandler:
    def __init__(self, tcp_client: BaseTCPClient, server_address: tuple):
        self.tcp_client: BaseTCPClient = tcp_client
        self.server_address: tuple = server_address
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
    def __init__(self, server_address: tuple, server_socket_handler: ServerSocketHandler):
        self.server_address = server_address
        self.server_socket_handler = server_socket_handler
        self.tasks = []
        self.counter = 0

    async def add_client(self, client_tcp_client, start_message: BaseMessage = None):
        server_client = BaseTCPClient()
        await server_client.connect(self.server_address)
        await server_client.send(start_message)
        bridge = Bridge(server_client, client_tcp_client)
        self.counter += 1
        task = None
        try:
            change_tasks = [asyncio.create_task(self.not_change()), asyncio.create_task(self.change(client_tcp_client))]
            done, pending = await asyncio.wait(change_tasks, return_when=asyncio.FIRST_COMPLETED)
            feature, = done
            for task in change_tasks:
                if not task.done():
                    task.cancel()
            if feature.result():
                print("change happened in group chatroom")
                message = {
                    "type": "change_game"
                }

                await self.server_socket_handler.tcp_client.send(BaseMessage(message))
                return
            task = asyncio.create_task(bridge.run_full_duplex())
            self.tasks.append(task)
            await task
        except ClientConnectionException:
            self.tasks.remove(task)
            raise

    async def change(self, tcp_client: BaseTCPClient):
        print("in change")
        while True:
            message = await tcp_client.receive()
            print(message)
            json_content = message.content
            if json_content['type'] == "change_game" and self.counter <= 1:
                return True

    async def not_change(self):
        print("in not_change")
        while True:
            if self.counter >= 2:
                print("not_change return")
                return False
            await asyncio.sleep(1)


class GameServersSocketServer:
    def __init__(self, host, port):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.loop = asyncio.get_event_loop()
        self.all_sockets: list[ServerSocketHandler] = []
        self.unallocated_sockets: list[ServerSocketHandler] = []
        self.waiting_sockets_by_userid: dict[str: ServerSocketHandler] = dict()
        self.group_chat_rooms: list[GroupChatRoom] = []
        self.unallocated_group_chat_rooms: list[GroupChatRoom] = []
        self.waiting_chats_by_userid = dict()

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.tcp_server.accept()
            logger.info('A new GameServer socket accepted')
            handshake_message = await tcp_client.receive()
            server_address = (handshake_message.content["host"], handshake_message.content["port"])
            logger.info(f'The new GameServer is located at {server_address}')
            server_socket_handler = ServerSocketHandler(tcp_client, server_address)

            self.all_sockets.append(server_socket_handler)
            self.unallocated_sockets.append(server_socket_handler)

            self.loop.create_task(server_socket_handler.handle_unmanaged_socket(tcp_client))

    def get_waiting_socket(self, username):
        if username in self.waiting_sockets_by_userid:
            print("poped from waiting sockets")
            return self.waiting_sockets_by_userid.pop(username)
        return None

    async def pop_unallocated_socket(self) -> ServerSocketHandler:
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

                tcp_server_client = handler.tcp_client
                await tcp_server_client.send(BaseMessage(abort_message))
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
                tcp_server_client = handler.tcp_client
                await tcp_server_client.send(BaseMessage(abort_message))
                self.unallocated_sockets.append(handler)
                handler.state = handler.states[0]


class ClientSocketHandler:
    def __init__(self, tcp_client: BaseTCPClient, game_server_socket_server: GameServersSocketServer):
        self.tcp_client: BaseTCPClient = tcp_client
        self.game_server_socket_server = game_server_socket_server
        self.states = ['connected', "disconnected"]
        self.state = self.states[1]

    async def handle_unmanaged_socket(self, tcp_client: BaseTCPClient):
        self.state = self.states[0]
        while True:
            try:
                message: BaseMessage = await tcp_client.receive()
                json_content = message.content
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
            username = start_message.content['username']
            waiting_socket = self.game_server_socket_server.get_waiting_socket(username)
            if waiting_socket:
                unallocated_server_socket = waiting_socket
            else:
                unallocated_server_socket: ServerSocketHandler = await self.game_server_socket_server.pop_unallocated_socket()

            tcp_server_client = unallocated_server_socket.tcp_client

            unallocated_server_socket.state = unallocated_server_socket.states[1]

            try:
                if waiting_socket:
                    print("sending reconnect message")
                    reconnect_message = {
                        "type": "reconnect",
                        "username": username
                    }
                    await tcp_server_client.send(BaseMessage(reconnect_message))
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
                    await tcp_client.send(BaseMessage(server_assigned_message))
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

                await tcp_client.send(BaseMessage(server_crashed_message))
                break
            except ClientConnectionException:
                self.game_server_socket_server.move_to_waiting(username, unallocated_server_socket)
                raise ClientConnectionException("error")

            unallocated_server_socket.state = unallocated_server_socket.states[0]
            self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
            break

    async def handle_multi_player_game(self, tcp_client: BaseTCPClient, start_message: BaseMessage):
        while True:
            username = start_message.content['username']
            chat_room = self.game_server_socket_server.pop_unallocated_chat_room()
            if chat_room is None:
                tasks = [asyncio.create_task(x) for x in [self.change_requested(tcp_client),
                                                          self.game_server_socket_server.pop_unallocated_socket()]]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                feature, = done
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if type(feature.result()) != ServerSocketHandler:
                    print("returned in handle_multi_player_game")
                    return

                unallocated_server_socket : ServerSocketHandler = feature.result()
                tcp_server_client = unallocated_server_socket.tcp_client

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
                    await tcp_client.send(BaseMessage(server_assigned_message))
                except SocketClosedException:
                    unallocated_server_socket.state = unallocated_server_socket.states[0]
                    self.game_server_socket_server.unallocated_sockets.append(unallocated_server_socket)
                    raise ClientConnectionException("error")

                logger.debug("before creating chatroom")
                chat_room = GroupChatRoom(unallocated_server_socket.server_address,
                                          unallocated_server_socket)
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

                await tcp_client.send(BaseMessage(server_crashed_message))
                break
            except ClientConnectionException:
                self.game_server_socket_server.move_to_waiting_chat_rooms(username, chat_room)
                raise ClientConnectionException("error")
            break

        if all(task.done() for task in chat_room.tasks):
            if chat_room.server_socket_handler not in self.game_server_socket_server.unallocated_sockets:
                self.game_server_socket_server.unallocated_sockets.append(chat_room.server_socket_handler)
                chat_room.server_socket_handler.state = chat_room.server_socket_handler.states[0]

    async def change_requested(self, tcp_client: BaseTCPClient):
        while True:
            message = await tcp_client.receive()
            json_content = message.content
            if json_content['type'] == "change_game":
                return True


class ClientsSocketServer:
    def __init__(self, host, port, game_server_socket_server: GameServersSocketServer):
        self.tcp_server = BaseTCPServer(host, port, backlog=5)
        self.game_server_socket_server = game_server_socket_server
        self.loop = asyncio.get_event_loop()
        self.client_handlers = []

    async def accept(self):
        logger.info(f'start of SocketServer-accept with host={self.tcp_server.host} and port={self.tcp_server.port}')

        while True:
            tcp_client: BaseTCPClient = await self.tcp_server.accept()
            logger.debug("A new user socket accepted.")
            client_socket_handler = ClientSocketHandler(tcp_client, self.game_server_socket_server)
            self.client_handlers.append(client_socket_handler)
            self.loop.create_task(client_socket_handler.handle_unmanaged_socket(tcp_client))

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
    logger.info('start of start_webserver')
    game_server_socket_server = GameServersSocketServer(WEBSERVER_HOST, WEBSERVER_GAME_SERVER_PORT)
    clients_socket_server = ClientsSocketServer(WEBSERVER_HOST, WEBSERVER_CLIENT_SERVER_PORT, game_server_socket_server)
    await asyncio.gather(*[
        asyncio.create_task(clients_socket_server.accept()),
        asyncio.create_task(game_server_socket_server.accept()),
        asyncio.create_task(control_console(game_server_socket_server, clients_socket_server))
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
