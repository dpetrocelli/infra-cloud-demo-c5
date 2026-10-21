"""Class 5 demo API: the class 4 API, now behind a web frontend.

GET  /         -> who answers: message, version (baked in at build time) and hostname
GET  /healthz  -> {"status": "ok"} for the smoke test and the deploy check
GET  /items    -> the items saved in DATA_DIR (survive a container restart if /data is a volume)
POST /items    -> {"nombre": "..."} appends one item
GET  /votos    -> the poll: each option with its count
POST /votos/{opcion} -> one more vote for that option
GET  /aplausos -> total claps and how many each web Pod handled
POST /aplausos -> one more clap, counted for the web Pod in X-Web-Pod
GET  /docs     -> Swagger UI, to try everything from the browser
"""

import json
import os
import socket
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
ITEMS_FILE = DATA_DIR / "items.json"
VOTES_FILE = DATA_DIR / "votos.json"
CLAPS_FILE = DATA_DIR / "aplausos.json"
OPTIONS = ["re-bien", "mas-o-menos", "me-exploto", "sueno"]

# The whole class votes at once: one write at a time, so no vote gets lost.
lock = threading.Lock()

app = FastAPI(title="demo-c5", version=APP_VERSION)


class Item(BaseModel):
    nombre: str


def _read_items() -> list[dict]:
    if not ITEMS_FILE.exists():
        return []
    return json.loads(ITEMS_FILE.read_text())


@app.get("/")
def root() -> dict:
    return {
        "mensaje": "Hola desde la API de la clase 5",
        "version": APP_VERSION,
        "host": socket.gethostname(),
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/items")
def list_items() -> list[dict]:
    return _read_items()


@app.post("/items", status_code=201)
def create_item(item: Item) -> dict:
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        items = _read_items()
        new = {"nombre": item.nombre, "creado": int(time.time())}
        items.append(new)
        ITEMS_FILE.write_text(json.dumps(items))
    return new


def _read_votes() -> dict:
    votes = json.loads(VOTES_FILE.read_text()) if VOTES_FILE.exists() else {}
    return {o: votes.get(o, 0) for o in OPTIONS}


@app.get("/votos")
def list_votes() -> dict:
    return _read_votes()


@app.post("/votos/{opcion}")
def vote(opcion: str) -> dict:
    if opcion not in OPTIONS:
        raise HTTPException(status_code=404, detail="opción inexistente")
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        votes = _read_votes()
        votes[opcion] += 1
        VOTES_FILE.write_text(json.dumps(votes))
    return votes


def _read_claps() -> dict:
    if not CLAPS_FILE.exists():
        return {"total": 0, "pods": {}}
    return json.loads(CLAPS_FILE.read_text())


@app.get("/aplausos")
def list_claps() -> dict:
    claps = _read_claps()
    claps["ahora"] = int(time.time())  # the page compares it with "ultimo" to fade old Pods
    return claps


@app.post("/aplausos")
def clap(x_web_pod: str = Header(default="sin-nombre")) -> dict:
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        claps = _read_claps()
        claps["total"] += 1
        pod = claps["pods"].setdefault(x_web_pod, {"n": 0, "ultimo": 0})
        pod["n"] += 1
        pod["ultimo"] = int(time.time())
        CLAPS_FILE.write_text(json.dumps(claps))
    claps["ahora"] = int(time.time())
    return claps
