import os
from pathlib import Path
from tikcli.config import CONFIG_DIR, SESSION_FILE, RAM_DIR, DOWNLOAD_DIR


def test_config_directories():
    assert isinstance(CONFIG_DIR, Path)
    assert CONFIG_DIR.exists()
    assert isinstance(SESSION_FILE, Path)
    assert isinstance(RAM_DIR, Path)
    assert RAM_DIR.exists()
    assert isinstance(DOWNLOAD_DIR, Path)
    assert DOWNLOAD_DIR.exists()


def test_ram_dir_writable():
    test_file = RAM_DIR / "test_write.tmp"
    test_file.write_text("ok")
    assert test_file.read_text() == "ok"
    test_file.unlink()


def test_get_default_vo_driver():
    from tikcli.config import get_default_vo_driver
    driver = get_default_vo_driver()
    assert driver in ("sixel", "mpv")

