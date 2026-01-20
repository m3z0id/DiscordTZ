import copy

from server.protocol.Response import Response


class DeepCopier(type):
    def __getattribute__(cls, name: str) -> object:
        return copy.deepcopy(super().__getattribute__(name))


class ErrorCode(metaclass=DeepCopier):
    OK = Response(200, "OK")
    BAD_REQUEST = Response(400, "Bad Request")
    FORBIDDEN = Response(403, "Forbidden")
    NOT_FOUND = Response(404, "Not Found")
    BAD_METHOD = Response(405, "Bad Method")
    INTERNAL_SERVER_ERROR = Response(500, "Internal Server Error")
    CONFLICT = Response(409, "Conflict")
    BAD_GEOLOC = Response(-1, "Bad Geolocation")