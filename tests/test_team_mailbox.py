"""Tests for team mailbox system."""

import json

import pytest

from vibesop.core.team.mailbox import Mailbox, Message


def test_send_and_receive(tmp_path):
    mailbox = Mailbox(tmp_path / "mailbox")
    msg = Message(sender="coordinator", recipient="worker-1", content="Do task A")
    mailbox.send(msg)

    received = mailbox.receive("worker-1")
    assert received is not None
    assert received.sender == "coordinator"
    assert received.recipient == "worker-1"
    assert received.content == "Do task A"


def test_receive_nonexistent(tmp_path):
    mailbox = Mailbox(tmp_path / "mailbox")
    received = mailbox.receive("nonexistent")
    assert received is None


def test_clear_mailbox(tmp_path):
    mailbox = Mailbox(tmp_path / "mailbox")
    mailbox.send(Message(sender="coord", recipient="w1", content="test"))
    assert mailbox.clear("w1") is True
    assert mailbox.receive("w1") is None


def test_clear_nonexistent(tmp_path):
    mailbox = Mailbox(tmp_path / "mailbox")
    assert mailbox.clear("nonexistent") is False


def test_list_pending(tmp_path):
    mailbox = Mailbox(tmp_path / "mailbox")
    mailbox.send(Message(sender="coord", recipient="w1", content="task 1"))
    mailbox.send(Message(sender="coord", recipient="w2", content="task 2"))

    pending = mailbox.list_pending()
    assert len(pending) == 2
    assert "w1" in pending
    assert "w2" in pending


def test_message_to_dict():
    msg = Message(sender="a", recipient="b", content="hello", metadata={"key": "val"})
    d = msg.to_dict()
    assert d["sender"] == "a"
    assert d["recipient"] == "b"
    assert d["content"] == "hello"
    assert d["metadata"]["key"] == "val"


def test_message_from_dict():
    data = {
        "sender": "a",
        "recipient": "b",
        "content": "hi",
        "timestamp": "2024-01-01",
        "metadata": {},
    }
    msg = Message.from_dict(data)
    assert msg.sender == "a"
    assert msg.content == "hi"
