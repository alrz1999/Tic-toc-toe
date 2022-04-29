import asyncio
import socket
import struct

from utils import json_encode, json_decode


class BaseMessage:
    def __init__(self, json_header: dict, content: bytes):
        self.json_header: dict = json_header
        self.content: bytes = content

    def encode(self):
        json_header = {
            "content-encoding": self.json_header.get('content-encoding'),
            "content-length": len(self.content)
        }

        json_header_bytes = json_encode(json_header, 'utf-8')
        json_header_length = struct.pack(">H", len(json_header_bytes))
        return json_header_length + json_header_bytes + self.content


class SocketClosedException(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)

        if errors is None:
            errors = []
        self.errors = errors


class BaseTCPClient:
    JSON_HEADER_LENGTH = 2

    def __init__(self, host: str, port: int, sock: socket.socket = None):
        self.host = host
        self.port = port
        self.sock = sock
        self.is_open = False
        if sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.is_open = True
        self.loop = asyncio.get_event_loop()

    async def send(self, message: BaseMessage):
        print(f"trying to send message with content={message.content}")
        message_bytes = message.encode()
        try:
            await self.loop.sock_sendall(self.sock, message_bytes)
        except:
            raise SocketClosedException("socket is not open. happened in send")
        print(f"message sended")

    async def receive(self) -> BaseMessage:
        header_length = await self.read_json_header_length()
        json_header = await self.read_json_header(header_length)
        content = await self.read_message_content(json_header)
        return BaseMessage(json_header, content)

    async def read_json_header_length(self) -> int:
        raw_data = await self.loop.sock_recv(self.sock, BaseTCPClient.JSON_HEADER_LENGTH)
        if len(raw_data) == 0:
            self.is_open = False
            raise SocketClosedException("socket is not open. happened in receive")
        # print("read_json_header_length = ", raw_data)
        return struct.unpack(">H", raw_data)[0]

    async def read_json_header(self, header_length: int) -> dict:
        raw_data = await self.loop.sock_recv(self.sock, header_length)
        # print("read_json_header = ", raw_data)
        json_header = json_decode(raw_data, 'utf-8')
        # for request_header in ("byteorder", "content-length", "content-type", "content-encoding",):
        #     if request_header not in json_header:
        #         raise ValueError(f"Missing required header '{request_header}'.")
        return json_header

    async def read_message_content(self, json_header: dict) -> bytes:
        content_length = json_header['content-length']
        raw_data = await self.loop.sock_recv(self.sock, content_length)
        # print("read_message_content = ", raw_data)
        return raw_data
        # if json_header["content-type"] == "text/json":
        #     encoding = json_header["content-encoding"]
        #     content = self.json_decode(raw_data)
        #     print(f"Received request {self.request!r} from {self.addr}")

        pass

    async def connect(self):
        self.sock.setblocking(False)
        await self.loop.sock_connect(self.sock, (self.host, self.port))
        self.is_open = True

    async def is_connected(self):
        return self.is_open

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.sock.close()
