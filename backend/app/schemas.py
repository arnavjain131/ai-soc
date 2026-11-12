import json
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SecurityEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_event_id: str = Field(min_length=1, max_length=128)
    event_time: datetime
    event_type: Literal['LOGIN_FAILED', 'LOGIN_SUCCEEDED']
    source_ip: str
    destination_ip: str
    destination_port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
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


class EventBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[SecurityEvent] = Field(min_length=1, max_length=100)


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['open', 'investigating', 'closed', 'false_positive']


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
