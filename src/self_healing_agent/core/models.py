from pydantic import BaseModel, Field


class IncidentPayload(BaseModel):
    incident_details: str = Field(
        ...,
        description="Raw incident details received from the source system.",
    )
