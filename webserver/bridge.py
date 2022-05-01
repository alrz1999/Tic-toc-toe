import asyncio
import logging

import utils
from transport.tcp_client import BaseTCPClient, BaseMessage, SocketClosedException
from webserver.exceptions import ClientConnectionException, ServerConnectionException

logging.basicConfig(format='%(asctime)s %(lineno)d %(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Bridge:
    def __init__(self, server: BaseTCPClient, client: BaseTCPClient):
        self.server: BaseTCPClient = server
        self.client: BaseTCPClient = client
        self.quit = False

    async def run_full_duplex(self):
        tasks = [
            asyncio.create_task(self.forward_from_server_to_client()),
            asyncio.create_task(self.forward_from_client_to_server())
        ]
        try:
            await utils.wait_until_first_completed(tasks)
        except SocketClosedException:
            print('socket closed exception caught in Bridge.')
            raise

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
