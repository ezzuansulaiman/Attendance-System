import asyncio
from types import SimpleNamespace

from bot.worker_handlers import _send_navigation_menu


class DummyMessage:
    def __init__(self, chat_type: str) -> None:
        self.chat = SimpleNamespace(type=chat_type)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append({"text": text, **kwargs})


def _button_texts(reply_markup) -> list[str]:
    return [button.text for row in reply_markup.keyboard for button in row]


def test_send_navigation_menu_shows_worker_button_in_group_without_admin_button() -> None:
    message = DummyMessage("group")

    asyncio.run(_send_navigation_menu(message, show_worker_menu=True, show_admin_menu=True))

    assert len(message.answers) == 1
    buttons = _button_texts(message.answers[0]["reply_markup"])
    assert "Menu Kehadiran" in buttons
    assert "Menu Admin" not in buttons


def test_send_navigation_menu_keeps_worker_and_admin_buttons_in_private_chat() -> None:
    message = DummyMessage("private")

    asyncio.run(_send_navigation_menu(message, show_worker_menu=True, show_admin_menu=True))

    assert len(message.answers) == 1
    buttons = _button_texts(message.answers[0]["reply_markup"])
    assert "Menu Kehadiran" in buttons
    assert "Menu Admin" in buttons
