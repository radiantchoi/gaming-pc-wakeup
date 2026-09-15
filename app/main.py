from fastapi import FastAPI, Header, HTTPException

from app.config import load_settings
from app.wol import format_mac, is_port_open, send_magic_packet

app = FastAPI()
settings = load_settings()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/wake")
def wake(x_token: str | None = Header(default=None)) -> dict[str, str | int]:
    if settings.token is not None and x_token != settings.token:
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        send_magic_packet(settings.mac, settings.broadcast, settings.port)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "status": "sent",
        "mac": format_mac(settings.mac),
        "broadcast": settings.broadcast,
        "port": settings.port,
    }


@app.get("/status")
def status() -> dict[str, str | int | bool]:
    online = is_port_open(settings.host, settings.status_port, settings.status_timeout)
    return {"online": online, "host": settings.host, "port": settings.status_port}
