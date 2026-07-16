"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .routes import files as files_routes
from .routes import patients as patients_routes
from .routes import projects as projects_routes
from .routes import prompts as prompts_routes
from .routes import settings as settings_routes
from .routes import stages as stages_routes
from .routes import export as export_routes
from .routes import tools as tools_routes
from .routes import pipeline as pipeline_routes
from .routes import agent_organize as agent_organize_routes
from .ws import manager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Medora Backend", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_routes.router)
app.include_router(prompts_routes.router)
app.include_router(patients_routes.router)
app.include_router(settings_routes.router)
app.include_router(stages_routes.router)
app.include_router(export_routes.router)
app.include_router(files_routes.router)
app.include_router(tools_routes.router)
app.include_router(pipeline_routes.router)
app.include_router(agent_organize_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
