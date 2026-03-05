from fastapi import FastAPI

from self_healing_agent import __version__
from self_healing_agent.core.models import IncidentPayload
from self_healing_agent.agent.service import run_incident

def create_app() -> FastAPI:
    app = FastAPI(
        title="Self Healing Agent",
        description="Control plane API for the self-healing agent.",
        version=__version__,
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "self-healing-agent", "status": "ok", "version": __version__}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/incident")
    def ingest_incident(payload: IncidentPayload) -> dict[str, object]:
        response =run_incident(payload)
        return {
            "status": "accepted",
            "payload": response,
        }

    return app


app = create_app()
