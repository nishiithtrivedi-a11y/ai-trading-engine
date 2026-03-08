"""UI navigation architecture safeguards."""

from pathlib import Path


def test_streamlit_builtin_sidebar_navigation_is_disabled() -> None:
    cfg = Path(".streamlit/config.toml")
    assert cfg.exists(), ".streamlit/config.toml should exist for dashboard nav control"
    text = cfg.read_text(encoding="utf-8")
    assert "showSidebarNavigation = false" in text


def test_all_pages_have_standalone_entrypoint() -> None:
    pages_dir = Path("src/ui/pages")
    page_files = [p for p in pages_dir.glob("*.py") if p.name != "__init__.py"]
    assert page_files, "Expected Streamlit page modules under src/ui/pages"

    for path in page_files:
        text = path.read_text(encoding="utf-8")
        assert 'if __name__ == "__main__":' in text, f"Missing standalone entrypoint: {path.name}"
