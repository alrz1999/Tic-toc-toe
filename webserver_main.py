import asyncio
import logging

from utils import async_input
from webserver.chatroom import ChatroomRepository
from webserver.web_server import ClientRepository, GameServerRepository

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_GAMESERVER_REPO_PORT = 9090
WEBSERVER_CLIENT_REPO_PORT = 8989


async def control_console(gameserver_repo: GameServerRepository,
                          client_repo: ClientRepository):
    while True:
        print("WebServer Console".center(40, '*'))
        line = await async_input("available commands:\n/users\n/servers\n")
        if line == '/users':
            print("number of connected clients: ", client_repo.get_number_of_connected_clients())
        elif line == '/servers':
            print("number of running servers: ", gameserver_repo.get_number_of_connected_gameservers())


async def start_webserver():
    logger.info('start of start_webserver')
    chatroom_repo = ChatroomRepository()
    gameserver_repo = GameServerRepository(WEBSERVER_HOST, WEBSERVER_GAMESERVER_REPO_PORT, chatroom_repo)
    client_repo = ClientRepository(WEBSERVER_HOST, WEBSERVER_CLIENT_REPO_PORT, chatroom_repo)
    await asyncio.gather(*[
        asyncio.create_task(gameserver_repo.accept_gameserver()),
        asyncio.create_task(client_repo.accept_client()),
        asyncio.create_task(control_console(gameserver_repo, client_repo))
    ])
    logger.info('end of start_webserver')


if __name__ == '__main__':
    asyncio.run(start_webserver())
