class ExitGameException(Exception):
    def __init__(self, message):
        super(ExitGameException, self).__init__(message)
