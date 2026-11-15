REFUSED = 1
ENVIRONMENT = 2


class CliError(Exception):
    def __init__(self, message: str, code: int = ENVIRONMENT) -> None:
        super().__init__(message)
        self.code = code
