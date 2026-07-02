import abc


class BaseError(Exception, abc.ABC):
    def __init__(self, message: str, code: str) -> None:
        self.message = message
        self.code = code

    def json(self) -> dict[str, str]:
        return {
            "message": self.message,
            "code": self.code,
        }
