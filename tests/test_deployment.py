"""P23 smoke tests: deployment artifacts are present and coherent (no Docker daemon needed)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_serves_the_api():
    df = (ROOT / "Dockerfile").read_text("utf-8")
    assert "uvicorn" in df and "src.api.main:app" in df
    assert "EXPOSE 8000" in df
    assert "requirements.txt" in df                       # deps installed


def test_dockerignore_excludes_secrets_and_data():
    di = (ROOT / ".dockerignore").read_text("utf-8")
    assert ".env" in di and "data/" in di                 # keep secrets + runtime data out of the image


def test_env_example_lists_the_openrouter_key():
    env = (ROOT / ".env.example").read_text("utf-8")
    assert "OPENROUTER_API_KEY" in env                    # the single key the system needs


def test_compose_mounts_index_and_env():
    comp = (ROOT / "docker-compose.yml").read_text("utf-8")
    assert "8000:8000" in comp and ".env" in comp and "./data:/app/data" in comp
