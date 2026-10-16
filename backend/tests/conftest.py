import os

os.environ.setdefault("SCYTHE_DATABASE_URL", "postgresql+psycopg://scythe:scythe@localhost:5544/scythe_test")
os.environ["SCYTHE_GITHUB_FAKE"] = "1"
os.environ["SCYTHE_GITHUB_FAKE_PATH"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from scythe import auth, gh_sync, jobs  # noqa: E402
from scythe.github import FakeGitHub  # noqa: E402
from scythe.db import SessionLocal, engine  # noqa: E402

TABLES = ("files, blocks, cards, labels, spans, nodes, edges, sources, authors, entities, chunks, jobs, "
          "accounts, auth_sessions, login_codes, app_state")
FRONTEND = "http://localhost:5173/"
REPO = "scythe-dev/cards"


class _Inline:
    """Run background jobs synchronously so tests can assert on their results."""

    def submit(self, fn, *args):
        fn(*args)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    jobs._pool = _Inline()


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    auth._fake = FakeGitHub(None, repos=(REPO,))
    gh_sync._labels_seen.clear()
    yield


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    from scythe.main import app

    with TestClient(app) as c:
        sign_in(c)
        assert c.put("/api/github/repo", json={"repo": REPO}).status_code == 200
        topic = c.get("/api/topics", params={"q": "fiscal redistribution"}).json()[0]
        assert c.put("/api/topics/current", json={"topic_id": topic["id"]}).status_code == 200
        yield c


def sign_in(c: TestClient) -> str:
    """Fake-GitHub sign-in the way the frontend does it: login -> #/auth/<code> -> exchange -> bearer."""
    r = c.get("/api/auth/login", params={"return_to": FRONTEND}, follow_redirects=False)
    assert r.status_code == 303, r.text
    location = r.headers["location"]
    assert location.startswith(FRONTEND + "#/auth/")
    token = c.post("/api/auth/exchange", json={"code": location.rsplit("/", 1)[1]}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return location.rsplit("/", 1)[1]


@pytest.fixture
def fake_gh() -> FakeGitHub:
    return auth._fake


ARTICLE = (
    "Nuclear war would cause human extinction. Scientists at Rutgers University found that soot "
    "from burning cities would block sunlight for a decade.\n\n"
    "The resulting “nuclear winter” would collapse global agriculture, starving billions of "
    "people within two years. Alan Robock warned that no country would be spared."
)


@pytest.fixture
def source(client):
    r = client.post("/api/sources/paste", json=dict(
        text=ARTICLE, title="Nuclear Winter Study", authors=["Alan Robock", "Owen Toon"],
        publisher="Nature Food", published="2022-08-15",
    ))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def labels(client):
    return {lbl["name"]: lbl for lbl in client.get("/api/labels").json()}
