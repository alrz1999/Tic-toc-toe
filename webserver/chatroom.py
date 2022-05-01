import asyncio
import logging
import uuid

from transport.tcp_client import BaseTCPClient, BaseMessage
from transport.tcp_server import BaseTCPServer
from webserver.bridge import Bridge
from webserver.exceptions import ClientConnectionException

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ChatRoom:
    def __init__(self, server_address: tuple):
        self.server_address = server_address
        self.room_id = str(uuid.uuid1())

    async def add_client(self, client_tcp_client: BaseTCPClient, start_message: BaseMessage = None):
        server_client = BaseTCPClient()
        await server_client.connect(self.server_address)
        await server_client.send(start_message)
        bridge = Bridge(server_client, client_tcp_client)
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
