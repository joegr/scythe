from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, jobs, nlp, topics
from .config import settings
from .db import SessionLocal
from .routers import auth as auth_routes
from .routers import cards, graph, labels, library, search, sources, spacy_api
from .routers import topics as topic_routes
from .services import seed_labels


@asynccontextmanager
async def lifespan(app: FastAPI):
    nlp.get_nlp()  # load spaCy once, before the first request
    with SessionLocal() as session:
        seed_labels(session)
        topics.seed(session)
    jobs.resume_pending()
    yield


app = FastAPI(title="Scythe", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-GitHub-Api-Version"],
    expose_headers=["Content-Disposition"],
    # GitHub Pages (public) calling this API on localhost triggers Chrome's Private Network Access
    # preflight; opting in lets it through (newer Chrome also asks the user once).
    allow_private_network=True,
    max_age=600,
)

app.include_router(auth_routes.router, prefix="/api")
# Everything else requires a signed-in GitHub user.
for r in (library.router, cards.router, sources.router, labels.router, search.router, graph.router, spacy_api.router,
          topic_routes.router):
    app.include_router(r, prefix="/api", dependencies=[Depends(auth.current_account)])


if settings.github_fake:
    from .routers import fakegh

    app.include_router(fakegh.router)


@app.get("/healthz")
def healthz():
    return {"ok": True, "spacy_model": nlp.model_id()}
