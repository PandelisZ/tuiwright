"""Tests for tuiwright._record.codegen."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable
from pathlib import Path

from tuiwright._record.codegen import CodegenStyle, generate_test

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_cast(
    tmp_path: Path,
    events: Iterable[tuple[float, str, str]],
    *,
    width: int = 80,
    height: int = 24,
    title: str = "myapp",
) -> Path:
    """Materialise an asciinema v2 cast file under tmp_path."""
    path = tmp_path / "session.cast"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"version": 2, "width": width, "height": height, "title": title}) + "\n")
        for time_, kind, data in events:
            fh.write(json.dumps([time_, kind, data]) + "\n")
    return path


def parse(test_src: str) -> ast.Module:
    """Parse the generated source so we can assert structurally."""
    return ast.parse(test_src)


def call_names(tree: ast.AST) -> list[str]:
    """List all attribute names of method calls on a node like ``tui.X(...)``."""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "tui":
                out.append(node.func.attr)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyntax:
    def test_output_is_valid_python(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready\r\n"),
                (0.5, "i", "hi"),
                (0.6, "o", "Ready\r\ntyped: hi\r\n"),
            ],
        )
        src = generate_test(cast, command=["myapp"], test_name="test_x")
        # Parses cleanly.
        parse(src)
        # Contains the expected top-level declarations.
        assert "async def test_x" in src
        assert "pytestmark = pytest.mark.asyncio" in src

    def test_uses_recorded_command(self, tmp_path: Path) -> None:
        cast = write_cast(tmp_path, [(0.0, "o", "Ready")], title="python myapp.py")
        src = generate_test(cast)
        assert "python myapp.py" in src

    def test_override_command(self, tmp_path: Path) -> None:
        cast = write_cast(tmp_path, [(0.0, "o", "Ready")])
        src = generate_test(cast, command=["my", "binary", "--flag"])
        assert "['my', 'binary', '--flag']" in src


class TestActions:
    def test_type_call_emitted(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "hello"),
                (0.6, "o", "typed: hello"),
            ],
        )
        src = generate_test(cast)
        assert 'tui.type("hello")' in src

    def test_press_call_emitted(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "\r"),  # enter
                (0.6, "o", "newline"),
            ],
        )
        src = generate_test(cast)
        assert 'tui.press("enter")' in src

    def test_click_call_emitted(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "\x1b[<0;10;5M\x1b[<0;10;5m"),
                (0.6, "o", "clicked"),
            ],
        )
        src = generate_test(cast)
        assert "tui.click(row=4, col=9)" in src

    def test_paste_call_emitted(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "\x1b[200~pasted\x1b[201~"),
                (0.6, "o", "got it"),
            ],
        )
        src = generate_test(cast)
        assert 'tui.paste("pasted")' in src


class TestWaits:
    def test_wait_for_text_inserted_between_actions(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready (q to quit)\r\n"),
                (0.5, "i", "x"),
                (0.6, "o", "typed: special phrase here\r\n"),
                (1.0, "i", "y"),
            ],
        )
        src = generate_test(cast)
        assert "wait_for_text" in src

    def test_wait_for_stable_fallback(self, tmp_path: Path) -> None:
        # No fresh interesting text between inputs — should fall back to stable.
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "x"),
                (0.6, "o", ""),       # no output between inputs
                (1.0, "i", "y"),
            ],
        )
        src = generate_test(cast)
        assert "wait_for_stable" in src


class TestSnapshots:
    def test_marker_inserts_snapshot(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "i", "x"),
                (0.6, "o", "x"),
                (1.0, "m", "after-x"),
            ],
        )
        src = generate_test(cast)
        assert "snapshot(" in src
        assert "ScreenSnapshotExtension" in src
        assert "after-x" in src

    def test_no_marker_no_snapshot_import_unused(self, tmp_path: Path) -> None:
        # When there are no markers, the test still imports ScreenSnapshotExtension
        # (we always have it in the header) but doesn't call it.
        cast = write_cast(
            tmp_path,
            [(0.0, "o", "Ready"), (0.5, "i", "x"), (0.6, "o", "y")],
        )
        src = generate_test(cast)
        assert "tui.screen == snapshot" not in src

    def test_multiple_markers_get_unique_names(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [
                (0.0, "o", "Ready"),
                (0.5, "m", "one"),
                (1.0, "m", "two"),
                (1.5, "m", "three"),
            ],
        )
        src = generate_test(cast)
        for label in ("one", "two", "three"):
            assert f'name="{label}"' in src

    def test_marker_label_sanitised(self, tmp_path: Path) -> None:
        cast = write_cast(
            tmp_path,
            [(0.0, "o", "Ready"), (0.5, "m", "needs sanitising! @#$")],
        )
        src = generate_test(cast)
        # The unsafe chars should become underscores.
        assert "needs_sanitising" in src


class TestStyles:
    def test_coarse_collapses_text(self, tmp_path: Path) -> None:
        cast = write_cast(tmp_path, [(0.0, "o", "Ready"), (0.5, "i", "hello")])
        src = generate_test(cast, style=CodegenStyle.COARSE)
        assert 'tui.type("hello")' in src

    def test_faithful_splits_text_into_presses(self, tmp_path: Path) -> None:
        cast = write_cast(tmp_path, [(0.0, "o", "Ready"), (0.5, "i", "hi")])
        src = generate_test(cast, style=CodegenStyle.FAITHFUL)
        assert 'tui.press("h")' in src
        assert 'tui.press("i")' in src


class TestEmptyCast:
    def test_header_only(self, tmp_path: Path) -> None:
        cast = write_cast(tmp_path, [])
        src = generate_test(cast)
        # Still parses and contains the test function declaration.
        parse(src)
        assert "async def test_recorded" in src
