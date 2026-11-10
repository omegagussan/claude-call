from src.services.todo_storage import InMemoryTodoStorage, TodoStorage


class TodoService:
    """Service layer coordinating todo business logic with a pluggable storage interface."""

    def __init__(self, storage: TodoStorage | None = None) -> None:
        self.storage: TodoStorage = storage if storage is not None else InMemoryTodoStorage()

    def set_storage(self, storage: TodoStorage) -> None:
        self.storage = storage

    async def push(self, phone_number: str, item: str) -> list[str]:
        """Add new item to the end of the user's list."""
        return await self.storage.push(phone_number, item)

    async def pop(self, phone_number: str) -> str | None:
        """Retrieve and remove the oldest item from the list (FIFO)."""
        return await self.storage.pop(phone_number)

    async def list_items(self, phone_number: str) -> list[str]:
        """List all items on the user's list."""
        return await self.storage.list_items(phone_number)

    async def clear(self, phone_number: str) -> None:
        """Clear user's list."""
        await self.storage.clear(phone_number)


# Default global instance initialized with in-memory storage for local dev and tests
todo_service = TodoService()
