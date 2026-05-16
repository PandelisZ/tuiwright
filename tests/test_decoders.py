"""Tests for tuiwright._record.decoders.

Round-trip property: encoding via ``_input`` then decoding should produce
an action that's semantically equivalent to the original call.
"""

from __future__ import annotations

import pytest

from tuiwright._input import (
    encode_focus,
    encode_key,
    encode_mouse,
    encode_paste,
)
from tuiwright._record.decoders import RecordedAction, decode_input_stream

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec,expected_key",
    [
        ("enter", "enter"),
        ("tab", "tab"),
        ("escape", "escape"),
        ("backspace", "backspace"),
        ("up", "up"),
        ("down", "down"),
        ("left", "left"),
        ("right", "right"),
        ("home", "home"),
        ("end", "end"),
        ("pageup", "pageup"),
        ("pagedown", "pagedown"),
        ("insert", "insert"),
        ("delete", "delete"),
        ("f1", "f1"),
        ("f5", "f5"),
        ("f12", "f12"),
        ("shift+tab", "shift+tab"),
    ],
)
def test_named_key_roundtrip(spec: str, expected_key: str) -> None:
    actions = decode_input_stream(encode_key(spec))
    assert actions == [RecordedAction("press", {"key": expected_key})]


@pytest.mark.parametrize(
    "spec",
    [
        "ctrl+a",
        "ctrl+s",
        "ctrl+z",
        "alt+f",
        "alt+b",
    ],
)
def test_modifier_letter_roundtrip(spec: str) -> None:
    actions = decode_input_stream(encode_key(spec))
    assert actions == [RecordedAction("press", {"key": spec})]


@pytest.mark.parametrize(
    "spec",
    [
        "ctrl+up",
        "shift+left",
        "alt+down",
        "ctrl+shift+up",
    ],
)
def test_modifier_arrow_roundtrip(spec: str) -> None:
    actions = decode_input_stream(encode_key(spec))
    assert len(actions) == 1
    assert actions[0].kind == "press"
    assert actions[0].data["key"] == spec


@pytest.mark.parametrize("spec", ["ctrl+f5", "ctrl+shift+f5", "alt+f7"])
def test_modifier_function_roundtrip(spec: str) -> None:
    actions = decode_input_stream(encode_key(spec))
    assert actions == [RecordedAction("press", {"key": spec})]


# ---------------------------------------------------------------------------
# Text accumulation
# ---------------------------------------------------------------------------


class TestTextRuns:
    def test_plain_ascii(self) -> None:
        actions = decode_input_stream(b"hello world")
        assert actions == [RecordedAction("type", {"text": "hello world"})]

    def test_utf8_multibyte(self) -> None:
        actions = decode_input_stream("café 日本".encode())
        assert actions == [RecordedAction("type", {"text": "café 日本"})]

    def test_text_then_key(self) -> None:
        data = b"hello" + encode_key("enter") + b"world"
        actions = decode_input_stream(data)
        assert actions == [
            RecordedAction("type", {"text": "hello"}),
            RecordedAction("press", {"key": "enter"}),
            RecordedAction("type", {"text": "world"}),
        ]

    def test_text_split_by_control(self) -> None:
        data = b"a" + encode_key("ctrl+s") + b"b" + encode_key("tab") + b"c"
        actions = decode_input_stream(data)
        kinds = [a.kind for a in actions]
        assert kinds == ["type", "press", "type", "press", "type"]


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------


class TestMouse:
    def test_left_click(self) -> None:
        press = encode_mouse(button="left", row=5, col=10)
        release = encode_mouse(button="left", row=5, col=10, pressed=False)
        actions = decode_input_stream(press + release)
        assert actions == [
            RecordedAction("click", {"row": 4, "col": 9}),
        ]

    def test_right_click(self) -> None:
        press = encode_mouse(button="right", row=5, col=10)
        release = encode_mouse(button="right", row=5, col=10, pressed=False)
        actions = decode_input_stream(press + release)
        assert actions == [
            RecordedAction("click", {"row": 4, "col": 9, "button": "right"}),
        ]

    def test_wheel_down(self) -> None:
        data = encode_mouse(button="wheel_down", row=10, col=20)
        actions = decode_input_stream(data)
        assert actions == [
            RecordedAction(
                "scroll",
                {"row": 9, "col": 19, "direction": "down", "lines": 1},
            )
        ]

    def test_drag(self) -> None:
        press = encode_mouse(button="left", row=5, col=10)
        motion = encode_mouse(button="left", row=5, col=12, motion=True)
        release = encode_mouse(button="left", row=5, col=15, pressed=False)
        actions = decode_input_stream(press + motion + release)
        assert actions == [
            RecordedAction(
                "drag",
                {
                    "from_row": 4,
                    "from_col": 9,
                    "to_row": 4,
                    "to_col": 14,
                    "button": "left",
                },
            )
        ]

    def test_click_then_text(self) -> None:
        press = encode_mouse(button="left", row=3, col=4)
        release = encode_mouse(button="left", row=3, col=4, pressed=False)
        actions = decode_input_stream(press + release + b"hello")
        assert actions == [
            RecordedAction("click", {"row": 2, "col": 3}),
            RecordedAction("type", {"text": "hello"}),
        ]


# ---------------------------------------------------------------------------
# Paste & focus
# ---------------------------------------------------------------------------


class TestPasteAndFocus:
    def test_bracketed_paste(self) -> None:
        data = encode_paste("multi\nline content")
        actions = decode_input_stream(data)
        assert actions == [
            RecordedAction("paste", {"text": "multi\nline content"})
        ]

    def test_focus_in_out(self) -> None:
        data = encode_focus(True) + encode_focus(False)
        actions = decode_input_stream(data)
        assert actions == [
            RecordedAction("focus", {"in_": True}),
            RecordedAction("focus", {"in_": False}),
        ]


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------


class TestStream:
    def test_complex_session(self) -> None:
        data = (
            b"hello "                                                # type
            + encode_key("ctrl+s")                                    # press
            + b"world"                                                # type
            + encode_mouse(button="left", row=2, col=2)               # click
            + encode_mouse(button="left", row=2, col=2, pressed=False)
            + encode_paste("from clipboard")                          # paste
            + encode_focus(False)                                     # focus
        )
        actions = decode_input_stream(data)
        kinds = [a.kind for a in actions]
        assert kinds == [
            "type", "press", "type", "click", "paste", "focus",
        ]

    def test_empty_input(self) -> None:
        assert decode_input_stream(b"") == []
