"""Class 5 demo API: the class 4 API, now behind a web frontend and on top of Postgres.

GET  /         -> who answers: message, version (baked in at build time) and hostname
GET  /healthz  -> {"status": "ok"} if the database answers (smoke test, readiness probe)
GET  /items    -> the items saved in the database
POST /items    -> {"nombre": "..."} appends one item
GET  /votos    -> the poll: each option with its count
POST /votos/{opcion} -> one more vote for that option
GET  /aplausos -> total claps and how many each web Pod handled
POST /aplausos -> one more clap, counted for the web Pod in X-Web-Pod
GET  /docs     -> Swagger UI, to try everything from the browser

The API keeps nothing on its own disk: everything lives in the database, so it can
have many replicas. The connection comes from the standard Postgres variables
(PGHOST, PGDATABASE, PGUSER, PGPASSWORD): no password in the code or the image.
(Not DB_*: a Kubernetes Service called "db" already injects a DB_PORT variable.)
"""

import asyncio
import os
import socket
import time
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")
OPTIONS = ["re-bien", "mas-o-menos", "me-exploto", "sueno"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id     serial PRIMARY KEY,
    nombre text   NOT NULL,
    creado bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS votos (
    opcion text PRIMARY KEY,
    n      int  NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aplausos (
    pod    text   PRIMARY KEY,
    n      int    NOT NULL DEFAULT 0,
    ultimo bigint NOT NULL
);
"""


def _connect() -> psycopg.Connection:
    return psycopg.connect(connect_timeout=3)


def _init_schema() -> None:
    # The database may start after the API (docker compose, a fresh Pod): wait for it.
    deadline = time.time() + 60
    while True:
        try:
            with _connect() as conn:
                conn.execute(SCHEMA)
            return
        except psycopg.OperationalError:
            if time.time() > deadline:
                raise
            time.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_init_schema)
    yield


app = FastAPI(title="demo-c5", version=APP_VERSION, lifespan=lifespan)


class Item(BaseModel):
    nombre: str


@app.get("/")
def root() -> dict:
    return {
        "mensaje": "Hola desde la API de la clase 5",
        "version": APP_VERSION,
        "host": socket.gethostname(),
    }


@app.get("/healthz")
def healthz() -> dict:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="sin base de datos")
    return {"status": "ok"}


@app.get("/items")
def list_items() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT nombre, creado FROM items ORDER BY id").fetchall()
    return [{"nombre": nombre, "creado": creado} for nombre, creado in rows]


@app.post("/items", status_code=201)
def create_item(item: Item) -> dict:
    new = {"nombre": item.nombre, "creado": int(time.time())}
    with _connect() as conn:
        conn.execute("INSERT INTO items (nombre, creado) VALUES (%s, %s)", (new["nombre"], new["creado"]))
    return new


def _read_votes(conn: psycopg.Connection) -> dict:
    rows = dict(conn.execute("SELECT opcion, n FROM votos").fetchall())
    return {o: rows.get(o, 0) for o in OPTIONS}


@app.get("/votos")
def list_votes() -> dict:
    with _connect() as conn:
        return _read_votes(conn)


@app.post("/votos/{opcion}")
def vote(opcion: str) -> dict:
    if opcion not in OPTIONS:
        raise HTTPException(status_code=404, detail="opción inexistente")
    with _connect() as conn:
        # One atomic statement: the whole class votes at once and no vote gets lost.
        conn.execute(
            "INSERT INTO votos (opcion, n) VALUES (%s, 1) "
            "ON CONFLICT (opcion) DO UPDATE SET n = votos.n + 1",
            (opcion,),
        )
        return _read_votes(conn)


def _read_claps(conn: psycopg.Connection) -> dict:
    rows = conn.execute("SELECT pod, n, ultimo FROM aplausos ORDER BY pod").fetchall()
    return {
        "total": sum(n for _, n, _ in rows),
        "pods": {pod: {"n": n, "ultimo": ultimo} for pod, n, ultimo in rows},
        "ahora": int(time.time()),  # the page compares it with "ultimo" to fade old Pods
    }


@app.get("/aplausos")
def list_claps() -> dict:
    with _connect() as conn:
        return _read_claps(conn)


@app.post("/aplausos")
def clap(x_web_pod: str = Header(default="sin-nombre")) -> dict:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO aplausos (pod, n, ultimo) VALUES (%s, 1, %s) "
            "ON CONFLICT (pod) DO UPDATE SET n = aplausos.n + 1, ultimo = EXCLUDED.ultimo",
            (x_web_pod, int(time.time())),
        )
        return _read_claps(conn)
