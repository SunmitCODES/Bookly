import uuid
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID type when available, otherwise stores
    the value as a CHAR(36) string (e.g. on SQLite). Python-side values
    are always returned as uuid.UUID objects regardless of backend.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        # Python -> DB
        if value is None:
            return None
        if dialect.name == "postgresql":
            # psycopg2 accepts a uuid.UUID directly
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        # SQLite / others: store the canonical string form
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        # DB -> Python
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))
