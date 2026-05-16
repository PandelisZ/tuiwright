"""Unit tests for the Screen / Region model."""

from __future__ import annotations

from tuiwright._emulator import Emulator
from tuiwright.screen import Position, Screen


def make_screen(rendered: list[str], cols: int | None = None) -> Screen:
    """Build a Screen by feeding plain text rows to a fresh emulator."""
    cols = cols if cols is not None else max(len(r) for r in rendered)
    rows = len(rendered)
    emu = Emulator(cols=cols, rows=rows)
    payload = "\r\n".join(r.ljust(cols) for r in rendered)
    emu.feed(payload.encode("utf-8"))
    return Screen.from_emulator(emu)


class TestScreenBasics:
    def test_text_concatenates_rows(self) -> None:
        s = make_screen(["hello", "world"])
        assert s.text == "hello\nworld"

    def test_row_indexing(self) -> None:
        s = make_screen(["abc", "def"])
        assert s.row(0) == "abc"
        assert s.row(1) == "def"

    def test_default_cell(self) -> None:
        s = make_screen(["x"], cols=5)
        assert s.cells[0][0].char == "x"
        assert s.cells[0][1].char == " "
        assert s.cells[0][1].has_default_attrs()

    def test_dimensions(self) -> None:
        s = make_screen(["hello"], cols=10)
        assert s.cols == 10
        assert s.rows == 1


class TestSearch:
    def test_find_returns_positions(self) -> None:
        s = make_screen(["one two", "two one"])
        hits = s.find("two")
        assert hits == [Position(0, 4), Position(1, 0)]

    def test_find_regex(self) -> None:
        s = make_screen(["error 42", "warn 7"])
        hits = s.find(r"\d+", regex=True)
        assert {h.col for h in hits} >= {5, 6}

    def test_row_containing(self) -> None:
        s = make_screen(["nope", "yes target", "nope"])
        assert s.row_containing("target") == 1
        assert s.row_containing("missing") is None

    def test_contains(self) -> None:
        s = make_screen(["hi"])
        assert s.contains("hi")
        assert not s.contains("bye")


class TestEquality:
    def test_two_identical_screens_are_equal(self) -> None:
        a = make_screen(["same", "rows"])
        b = make_screen(["same", "rows"])
        assert a == b

    def test_differing_text_unequal(self) -> None:
        a = make_screen(["one"])
        b = make_screen(["two"])
        assert a != b


class TestRegion:
    def test_explicit_rows_cols(self) -> None:
        s = make_screen(["aaaa", "bbbb", "cccc", "dddd"])
        r = s.region(rows=(1, 3), cols=(0, 4))
        assert r.text == "bbbb\ncccc"
        assert r.rows == 2
        assert r.cols == 4

    def test_titled_region_detection(self) -> None:
        s = make_screen(
            [
                "┌─ Logs ──┐",
                "│ line 1  │",
                "│ line 2  │",
                "└─────────┘",
            ]
        )
        r = s.region(title="Logs")
        assert r is not None
        assert "line 1" in r.text
        assert "line 2" in r.text

    def test_titled_region_missing(self) -> None:
        s = make_screen(["just text"])
        try:
            s.region(title="Logs")
        except LookupError:
            pass
        else:
            raise AssertionError("expected LookupError")
