import asyncio
import logging

from utils import async_input
from webserver.chatroom import ChatroomRepository
from webserver.web_server import ClientRepository, WebServer

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_GAMESERVER_REPO_PORT = 9090
WEBSERVER_CLIENT_REPO_PORT = 8989


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
