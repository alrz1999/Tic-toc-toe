from transport.tcp_client import BaseMessage, BaseTCPClient


class GameClient:
    def __init__(self, username: str, tcp_client: BaseTCPClient):
        self.username = username
        self.tcp_client: BaseTCPClient = tcp_client
        self.json_header = {}

    async def connect(self, server_address: tuple):
        # TODO: can be removed or useful
        await self.tcp_client.connect(server_address)

    async def send(self, content: dict):
        content['username'] = self.username
        base_message = BaseMessage(content)
        await self.tcp_client.send(base_message)

    async def receive(self):
        message: BaseMessage = await self.tcp_client.receive()
        return message.content
