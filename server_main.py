import asyncio
import logging
import random

import webserver_main
from server.game_server import GameServer
from server.tic_toc_toe import TicTocToe
from transport.tcp_client import BaseTCPClient, BaseMessage

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

WEBSERVER_HOST = webserver_main.WEBSERVER_HOST
WEBSERVER_PORT = webserver_main.WEBSERVER_GAMESERVER_REPO_PORT
WEBSERVER_ADDRESS = (WEBSERVER_HOST, WEBSERVER_PORT)

SERVER_HOST = '127.0.0.1'
SERVER_PORT = random.randint(10000, 50000)
SERVER_ADDRESS = (SERVER_HOST, SERVER_PORT)


async def async_handshake(tcp_client: BaseTCPClient):
    content = {
        "type": "handshake",
        "host": SERVER_HOST,
        "port": SERVER_PORT
    }

    await tcp_client.send(BaseMessage(content))


async def run_server():
    master_client = BaseTCPClient()
    await master_client.connect(WEBSERVER_ADDRESS)
    await async_handshake(master_client)
    game_server = GameServer(master_client, SERVER_HOST, SERVER_PORT)
    try:
        await game_server.start()
    finally:
        game_server.tcp_server.close()
        master_client.close()


if __name__ == '__main__':
    asyncio.run(run_server())


def test_tic_toc_toe():
    a = 'a'
    b = 'b'
    tic = TicTocToe(a, b)
    tic.place_mark(a, 1, 0)
    tic.place_mark(b, 0, 2)
    tic.place_mark(a, 0, 0)
    tic.place_mark(b, 1, 1)
    tic.place_mark(a, 2, 2)
    print(tic.has_game_finished())
    tic.place_mark(b, 2, 0)
    print(tic.has_game_finished())
