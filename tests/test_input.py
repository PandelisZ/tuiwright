"""Unit tests for the input encoder (no PTY, no async)."""

from __future__ import annotations

import pytest

from tuiwright._input import (
    LEFT,
    PASTE_END,
    PASTE_START,
    Mod,
    encode_focus,
    encode_key,
    encode_mouse,
    encode_paste,
    resolve_button,
)


class TestPlainKeys:
    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("enter", b"\r"),
            ("return", b"\r"),
            ("tab", b"\t"),
            ("space", b" "),
            ("escape", b"\x1b"),
            ("esc", b"\x1b"),
            ("backspace", b"\x7f"),
            ("up", b"\x1b[A"),
            ("down", b"\x1b[B"),
            ("right", b"\x1b[C"),
            ("left", b"\x1b[D"),
            ("home", b"\x1b[H"),
            ("end", b"\x1b[F"),
            ("pageup", b"\x1b[5~"),
            ("pagedown", b"\x1b[6~"),
            ("insert", b"\x1b[2~"),
            ("delete", b"\x1b[3~"),
            ("f1", b"\x1bOP"),
            ("f4", b"\x1bOS"),
            ("f5", b"\x1b[15~"),
            ("f12", b"\x1b[24~"),
        ],
    )
    def test_named_keys(self, spec: str, expected: bytes) -> None:
        assert encode_key(spec) == expected

    def test_single_char(self) -> None:
        assert encode_key("a") == b"a"
        assert encode_key("Z") == b"Z"
        assert encode_key("5") == b"5"


class TestModifiers:
    def test_ctrl_letter(self) -> None:
        assert encode_key("ctrl+a") == b"\x01"
        assert encode_key("ctrl+s") == b"\x13"
        assert encode_key("ctrl+z") == b"\x1a"

    def test_alt_letter(self) -> None:
        assert encode_key("alt+f") == b"\x1bf"

    def test_alt_ctrl_letter(self) -> None:
        assert encode_key("alt+ctrl+a") == b"\x1b\x01"

    def test_shift_letter(self) -> None:
        assert encode_key("shift+a") == b"A"

    def test_ctrl_arrow(self) -> None:
        assert encode_key("ctrl+up") == b"\x1b[1;5A"
        assert encode_key("ctrl+right") == b"\x1b[1;5C"

    def test_shift_arrow(self) -> None:
        assert encode_key("shift+left") == b"\x1b[1;2D"

    def test_alt_arrow(self) -> None:
        assert encode_key("alt+down") == b"\x1b[1;3B"

    def test_ctrl_function(self) -> None:
        # F5 with ctrl uses CSI N ; M ~
        assert encode_key("ctrl+f5") == b"\x1b[15;5~"
        # F1 with ctrl uses CSI 1 ; M X
        assert encode_key("ctrl+f1") == b"\x1b[1;5P"

    def test_shift_tab(self) -> None:
        assert encode_key("shift+tab") == b"\x1b[Z"

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown key"):
            encode_key("nope")

    def test_unknown_modifier_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown modifier"):
            encode_key("hyper+a")


class TestMouse:
    def test_left_press_sgr(self) -> None:
        assert encode_mouse(button="left", row=5, col=10) == b"\x1b[<0;10;5M"

    def test_left_release(self) -> None:
        assert encode_mouse(button="left", row=5, col=10, pressed=False) == b"\x1b[<0;10;5m"

    def test_right_press(self) -> None:
        assert encode_mouse(button="right", row=1, col=1) == b"\x1b[<2;1;1M"

    def test_wheel_up(self) -> None:
        assert encode_mouse(button="wheel_up", row=3, col=4) == b"\x1b[<64;4;3M"

    def test_modifier_bits(self) -> None:
        # ctrl = 16, shift = 4
        assert encode_mouse(
            button="left", row=2, col=2, modifiers=Mod.CTRL
        ) == b"\x1b[<16;2;2M"
        assert encode_mouse(
            button="left", row=2, col=2, modifiers=Mod.SHIFT | Mod.CTRL
        ) == b"\x1b[<20;2;2M"

    def test_motion_bit(self) -> None:
        assert encode_mouse(
            button="left", row=2, col=2, motion=True
        ) == b"\x1b[<32;2;2M"

    def test_resolve_button_aliases(self) -> None:
        assert resolve_button("left").code == 0
        assert resolve_button(LEFT) is LEFT

    def test_unknown_button(self) -> None:
        with pytest.raises(ValueError, match="unknown mouse button"):
            resolve_button("paw")


class TestPaste:
    def test_brackets_text(self) -> None:
        out = encode_paste("hello")
        assert out.startswith(PASTE_START)
        assert out.endswith(PASTE_END)
        assert b"hello" in out

    def test_collision_raises(self) -> None:
        with pytest.raises(ValueError, match="end marker"):
            encode_paste("oops \x1b[201~ bad")


class TestFocus:
    def test_focus_in(self) -> None:
        assert encode_focus(True) == b"\x1b[I"

    def test_focus_out(self) -> None:
        assert encode_focus(False) == b"\x1b[O"
