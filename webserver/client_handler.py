import asyncio
import enum
import logging

import utils
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from webserver.chatroom import ChatroomRepository, ChatRoom
from webserver.exceptions import ClientConnectionException, ServerConnectionException, ChangeGameException

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
        except ServerConnectionException:
            server_crashed_message = {
                "type": "server_crashed"
            }
            await tcp_client.send(BaseMessage(server_crashed_message))
        except ClientConnectionException:
            raise

    async def _handle_waiting_user_commands(self, tcp_client: BaseTCPClient):
        while True:
            message = await tcp_client.receive()
            message_type = message.content["type"]
            if message_type == "change_game":
                raise ChangeGameException("change_game requested")
