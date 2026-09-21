import sys
import pytest
from tikcli.client import TikTokClient
from tikcli.ui import TerminalUI, truncate_ansi, strip_ansi


def test_truncate_ansi_plain():
    s = "Hello World"
    assert truncate_ansi(s, 5) == "Hello"
    assert truncate_ansi(s, 20) == "Hello World"
    assert truncate_ansi(s, 0) == ""


def test_truncate_ansi_with_colors():
    s = "\033[1m\033[36mHello World\033[0m"
    truncated = truncate_ansi(s, 5)
    vis = strip_ansi(truncated)
    assert vis == "Hello"
    assert truncated.endswith("\033[0m")


def test_terminal_ui_modes_cycle():
    client = TikTokClient()
    ui = TerminalUI(client)
    assert ui.mode == "feed"

    ui.handle_input("TAB")
    assert ui.mode == "search"

    ui.handle_input("TAB")
    assert ui.mode == "creator"

    ui.handle_input("TAB")
    assert ui.mode == "dms"

    ui.handle_input("TAB")
    assert ui.mode == "feed"


def test_terminal_ui_number_shortcuts():
    client = TikTokClient()
    ui = TerminalUI(client)

    ui.handle_input("2")
    assert ui.mode == "search"

    ui.handle_input("3")
    assert ui.mode == "creator"

    ui.handle_input("4")
    assert ui.mode == "dms"

    ui.handle_input("1")
    assert ui.mode == "feed"


def test_terminal_ui_load_search(monkeypatch):
    client = TikTokClient()
    ui = TerminalUI(client)

    def mock_search(query, count=25):
        return [
            {"id": "1", "title": "video 1", "author_id": "creator1"},
            {"id": "2", "title": "video 2", "author_id": "creator2"},
        ]
    monkeypatch.setattr(client, "search_videos", mock_search)
    monkeypatch.setattr(ui, "draw", lambda: None)

    ui.load_search("pakistani videos")
    assert ui.mode == "search"
    assert len(ui.search_items) == 2
    assert ui.current_search_query == "pakistani videos"
    assert ui.search_index == 0


def test_terminal_ui_draw_row_positioning(monkeypatch):
    client = TikTokClient()
    ui = TerminalUI(client)
    ui.feed_items = [{"id": "1", "title": "Test Video", "author_id": "tester"}]

    output_chunks = []
    monkeypatch.setattr(sys.stdout, "write", lambda s: output_chunks.append(s))
    monkeypatch.setattr(sys.stdout, "flush", lambda: None)

    ui.draw()
    full_output = "".join(output_chunks)

    # Must contain row positioning escapes and line clears
    assert "\033[1;1H\033[2K" in full_output
    assert "\033[2;1H\033[2K" in full_output
    # Must NOT have trailing newlines at the end of draw buffer
    assert not full_output.endswith("\n")
    assert not full_output.endswith("\r\n")
