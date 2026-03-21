from typing import Any, Union

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers — each subgraph registers its own router here
# from research.router import router as research_router  # uncomment when ready

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# app.include_router(research_router, prefix="/research")  # uncomment when ready


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/echo")
def echo(body: Union[dict, list] = Body(...)) -> Any:
    return body
