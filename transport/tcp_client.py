import asyncio
import socket
import struct

from utils import json_encode, json_decode


class BaseMessage:
    def __init__(self, content):
        self.json_header: dict = {}
        self.content = content

    def encode(self):
        encoded_content = self._encode_content()

        json_header = {
            "content-length": len(encoded_content)
        }

        json_header_bytes = json_encode(json_header, encoding='utf-8')
        json_header_length = struct.pack(">H", len(json_header_bytes))
        return json_header_length + json_header_bytes + encoded_content

    def _encode_content(self) -> bytes:
        return json_encode(self.content, encoding='utf-8')


class SocketClosedException(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)

        if errors is None:
            errors = []
        self.errors = errors


class BaseTCPClient:
    JSON_HEADER_LENGTH = 2

    def __init__(self, sock: socket.socket = None, target_address: tuple = None):
        if sock is None:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.socket = sock
        self.target_address: tuple = target_address
        self.loop = asyncio.get_event_loop()

    async def send(self, message: BaseMessage):
        print(f"trying to send message with content={message.content}")
        message_bytes = message.encode()
        try:
            await self.loop.sock_sendall(self.socket, message_bytes)
        except:
            raise SocketClosedException("socket is not open. happened in send")
        print(f"message sent")

    async def receive(self) -> BaseMessage:
        header_length = await self.read_json_header_length()
        json_header = await self.read_json_header(header_length)
        content = await self.read_message_content(json_header)
        return BaseMessage(content)

    async def read_json_header_length(self) -> int:
        raw_data = await self.loop.sock_recv(self.socket, BaseTCPClient.JSON_HEADER_LENGTH)
        if len(raw_data) == 0:
            raise SocketClosedException("socket is not open. happened in receive")
        # print("read_json_header_length = ", raw_data)
        return struct.unpack(">H", raw_data)[0]

    async def read_json_header(self, header_length: int) -> dict:
        raw_data = await self.loop.sock_recv(self.socket, header_length)
        # print("read_json_header = ", raw_data)
        json_header = json_decode(raw_data, 'utf-8')
        # for request_header in ("byteorder", "content-length", "content-type", "content-encoding",):
        #     if request_header not in json_header:
        #         raise ValueError(f"Missing required header '{request_header}'.")
        return json_header

    async def read_message_content(self, json_header: dict):
        content_length = json_header['content-length']
        raw_data = await self.loop.sock_recv(self.socket, content_length)
        json_content = json_decode(raw_data, encoding='utf-8')
        # print("read_message_content = ", json_content)
        return json_content

    async def connect(self, server_address: tuple):
        self.socket.setblocking(False)
        await self.loop.sock_connect(self.socket, server_address)
        self.target_address = server_address

    async def connect_with_timeout(self, server_address, timeouts: list[int]):
        try:
            await self.connect(server_address)
        except ConnectionRefusedError:
            for timeout in timeouts:
                try:
                    print(f"ConnectionRefused. Can not connect to Host. Trying to reconnect after {timeout}s.")
                    await asyncio.sleep(timeout)
                    await self.connect(server_address)
                    break
                except ConnectionRefusedError:
                    pass
            else:
                print("Webserver is not available. Try another time.")
                raise ConnectionRefusedError

    def close(self):
        self.socket.close()
