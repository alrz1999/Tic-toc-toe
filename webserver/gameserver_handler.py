import logging

from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from webserver.chatroom import ChatRoom, ChatroomRepository

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
