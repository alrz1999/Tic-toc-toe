import asyncio
import socket

from transport.tcp_client import BaseTCPClient


class BaseTCPServer:
    def __init__(self, host: str, port: int, backlog=5):
        self.host = host
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((host, port))
        self.sock.listen(backlog)

        self.loop = asyncio.get_event_loop()

    async def accept(self):
        accepted_socket, address = await self.loop.sock_accept(self.sock)
        return BaseTCPClient(accepted_socket, address)

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sock.close()
