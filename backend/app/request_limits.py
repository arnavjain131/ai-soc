"""Bounded per-process admission control; credentials here are not authenticated."""
import hashlib
import math
import time
from dataclasses import dataclass

from starlette.datastructures import Headers
from starlette.responses import JSONResponse


@dataclass
class Bucket:
    tokens: float
    updated: float


class Admission:
    """Called on the ASGI event loop, without awaits between checking and reserving."""
    def __init__(self, settings, clock=time.monotonic, capacity=2048):
        self.settings, self.clock, self.capacity = settings, clock, capacity
        self.pools, self.credentials = {}, {}
        self.active = 0

    def consume(self, mapping, key, rate, burst, now):
        bucket = mapping.get(key)
        if bucket is None:
            if len(mapping) >= self.capacity:
                # Only discard fully refilled entries. Rotating credentials cannot
                # evict an exhausted bucket and obtain a fresh burst for that key.
                idle_ttl = max(120, self.settings.request_burst * 2)
                expired = [k for k, b in mapping.items() if now - b.updated >= idle_ttl]
                for old in expired:
                    del mapping[old]
                if len(mapping) >= self.capacity:
                    return 120
            bucket = mapping[key] = Bucket(float(burst), now)
        bucket.tokens = min(burst, bucket.tokens + max(0, now - bucket.updated) * rate / 60)
        bucket.updated = now
        if bucket.tokens < 1:
            return max(1, math.ceil((1 - bucket.tokens) * 60 / rate))
        bucket.tokens -= 1
        return 0

    def admit(self, group, credential):
        now = self.clock()
        ready = group == 'ready'
        delay = self.consume(self.pools, group, 60 if ready else self.settings.request_pool_per_minute,
                             10 if ready else self.settings.request_burst * 4, now)
        if delay:
            return delay
        if not ready:
            key = (group, hashlib.sha256(credential).digest() if credential else b'anonymous')
            delay = self.consume(self.credentials, key,
                                 self.settings.request_per_credential if credential else 30,
                                 self.settings.request_burst if credential else min(30, self.settings.request_burst), now)
            if delay:
                return delay
        if self.active >= self.settings.request_max_in_flight:
            return 1
        self.active += 1
        return 0


class RequestProtection:
    def __init__(self, app, admission):
        self.app, self.admission = app, admission

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or (scope['path'] == '/health/live' and scope['method'] == 'GET'):
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        group = 'ingest' if path == '/api/events/batch' else 'ready' if path == '/health/ready' else 'api'
        headers = Headers(scope=scope)
        credential = headers.get('x-source-token' if group == 'ingest' else 'authorization', '')
        maximum = 256 if group == 'ingest' else 8192
        # Malformed/oversized credentials share the anonymous budget, and are
        # rejected before DB/Auth access. Forwarded-IP headers are never read.
        malformed = len(credential) > maximum
        delay = self.admission.admit(group, b'' if malformed else credential.encode('latin-1'))
        if delay:
            return await JSONResponse(
                {'detail': 'Request limit reached. Wait and retry; telemetry queues should be retained.'},
                status_code=429, headers={'Retry-After': str(delay), 'Cache-Control': 'no-store'},
            )(scope, receive, send)
        try:
            if malformed:
                return await JSONResponse({'detail': 'Invalid authentication header'}, status_code=401)(scope, receive, send)
            await self.app(scope, receive, send)
        finally:
            self.admission.active -= 1
