import os
import sys

from fastapi import FastAPI

from self_healing_agent import __version__
from self_healing_agent.core.models import IncidentPayload
from self_healing_agent.agent.service import run_incident
from self_healing_agent.config.config_loader import load_env_from_config


def _read_env_name() -> str | None:
    allowed_envs = {"dev", "staging", "canary", "prod"}

    env_from_process = os.getenv("SHA_ENV")
    if env_from_process:
        normalized = env_from_process.strip().lower()
        if not normalized:
            return None
        if normalized not in allowed_envs:
            raise ValueError(
                f"Invalid SHA_ENV '{env_from_process}'. Allowed values: {sorted(allowed_envs)}"
            )
        return normalized

    for arg in sys.argv[1:]:
        if arg.startswith("env="):
            value = arg.split("=", 1)[1].strip().lower()
            if not value:
                return None
            if value not in allowed_envs:
                raise ValueError(
                    f"Invalid env '{arg}'. Allowed values: {sorted(allowed_envs)}"
                )
            return value
    return None


env = _read_env_name()
load_env_from_config(env=env or "dev")

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
