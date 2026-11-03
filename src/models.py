from pydantic import BaseModel


class CallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None


class FrokenUrRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None
    pause_seconds: float = 3.0


class TodoCallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None
