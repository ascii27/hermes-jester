"""Domain error types, mapped to HTTP status codes at the API boundary."""


class JesterError(Exception):
    """Base class for expected domain errors."""


class NotFoundError(JesterError):
    """A requested resource does not exist. -> 404"""


class ConflictError(JesterError):
    """A resource already exists or violates a uniqueness constraint. -> 409"""


class PayloadInvalidError(JesterError):
    """An item payload failed validation against its type's JSON Schema. -> 422"""


class SchemaInvalidError(JesterError):
    """A registered type's JSON Schema is itself not a valid schema. -> 422"""
