from transport.tcp_client import BaseMessage, BaseTCPClient
from utils import json_decode, json_encode


class GameClient:
    def __init__(self, username: str, tcp_client: BaseTCPClient):
        self.username = username
        self.tcp_client: BaseTCPClient = tcp_client
        self.json_header = {}

    async def connect(self):
        await self.tcp_client.connect()

    async def send(self, content: dict):
        content['username'] = self.username
        encoded_message = json_encode(content, encoding='utf-8')
        base_message = BaseMessage(self.json_header, encoded_message)
        await self.tcp_client.send(base_message)

    async def receive(self):
        message: BaseMessage = await self.tcp_client.receive()
        json_content: dict = json_decode(message.content, encoding='utf-8')
        return json_content
