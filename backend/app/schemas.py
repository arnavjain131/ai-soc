import json
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_event_id: str = Field(min_length=1, max_length=128)
    event_time: datetime
    source_ip: str
    destination_ip: str
    destination_port: int = Field(ge=1, le=65535)
    raw_data: dict = Field(default_factory=dict)

    @field_validator('event_time')
    @classmethod
    def utc_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('An explicit timezone is required')
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('Event time is too far in the future')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @field_validator('source_ip', 'destination_ip')
    @classmethod
    def valid_ip(cls, value):
        return str(ip_address(value))

    @field_validator('raw_data')
    @classmethod
    def bounded_raw(cls, value):
        if len(json.dumps(value).encode()) > 16384:
            raise ValueError('Raw event exceeds 16 KiB')
        return value


class SecurityEvent(EventFields):
    event_type: Literal['LOGIN_FAILED', 'LOGIN_SUCCEEDED']
    username: str = Field(min_length=1, max_length=128)


class NetworkRecord(EventFields):
    source_port: int = Field(strict=True, ge=1, le=65535)
    protocol: Literal['TCP', 'UDP']

    @field_validator('raw_data')
    @classmethod
    def collector_metadata_only(cls, value):
        if value != {'provenance': 'suricata_eve'}:
            raise ValueError('Only Suricata provenance metadata is accepted')
        return value


class NetworkFlow(NetworkRecord):
    event_type: Literal['NETWORK_FLOW']


class SuricataAlert(NetworkRecord):
    event_type: Literal['SURICATA_ALERT']
    signature_id: int = Field(strict=True, ge=1, le=2**32 - 1)
    signature: str = Field(min_length=1, max_length=256)
    severity: int = Field(strict=True, ge=1, le=255)


class EventBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[Annotated[SecurityEvent | NetworkFlow | SuricataAlert, Field(discriminator='event_type')]] = Field(
        min_length=1, max_length=100,
    )


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['open', 'investigating', 'closed', 'false_positive']


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
