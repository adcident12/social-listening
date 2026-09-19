import os

from sentiment import load_dotenv

def test_load_dotenv_basic(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_DOTENV_KEY", raising=False)
    monkeypatch.delenv("SL_DOTENV_2", raising=False)
    f = tmp_path / ".env"
    f.write_text("# comment line\n\nSL_DOTENV_KEY=value123\nSL_DOTENV_2=two\n", encoding="utf-8")
    load_dotenv(str(f))
    assert os.environ["SL_DOTENV_KEY"] == "value123"
    assert os.environ["SL_DOTENV_2"] == "two"
    monkeypatch.delenv("SL_DOTENV_KEY")
    monkeypatch.delenv("SL_DOTENV_2")

def test_load_dotenv_missing_file_ok(tmp_path):
    load_dotenv(str(tmp_path / "nope.env"))  # no error

def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_DOTENV_KEY", "real")
    f = tmp_path / ".env"
    f.write_text("SL_DOTENV_KEY=fake\n", encoding="utf-8")
    load_dotenv(str(f))
    assert os.environ["SL_DOTENV_KEY"] == "real"
