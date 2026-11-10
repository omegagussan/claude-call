import pytest

from src.services.todo_service import todo_service
from src.services.todo_speech import parse_todo_intent


@pytest.mark.asyncio
async def test_todo_service_push_pop_list():
    phone = "+46701234567"
    await todo_service.clear(phone)

    # Empty
    assert await todo_service.list_items(phone) == []
    assert await todo_service.pop(phone) is None

    # Push items (FIFO check)
    await todo_service.push(phone, "Apples")
    await todo_service.push(phone, "Milk")
    await todo_service.push(phone, "Bread")

    assert await todo_service.list_items(phone) == ["Apples", "Milk", "Bread"]

    # Pop removes oldest
    assert await todo_service.pop(phone) == "Apples"
    assert await todo_service.list_items(phone) == ["Milk", "Bread"]

    assert await todo_service.pop(phone) == "Milk"
    assert await todo_service.pop(phone) == "Bread"
    assert await todo_service.pop(phone) is None


def test_parse_todo_intent():
    assert parse_todo_intent("") == ("SILENCE", "")
    assert parse_todo_intent("   ") == ("SILENCE", "")
    assert parse_todo_intent("POP") == ("POP", "")
    assert parse_todo_intent("pop please") == ("POP", "")
    assert parse_todo_intent("LIST") == ("LIST", "")
    assert parse_todo_intent("list items") == ("LIST", "")
    assert parse_todo_intent("PUSH coffee beans") == ("PUSH", "coffee beans")
    assert parse_todo_intent("push") == ("PUSH", "")
    assert parse_todo_intent("random sentence") == ("UNKNOWN", "random sentence")
