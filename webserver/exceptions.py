class ServerConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class ClientConnectionException(Exception):
    def __init__(self, message):
        super().__init__(message)


class ChangeGameException(Exception):
    def __init__(self, message):
        super().__init__(message)
