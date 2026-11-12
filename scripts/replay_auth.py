"""Send a labelled synthetic authentication fixture to your local/private API.

Set SOC_SOURCE_TOKEN in your environment first. This is a pipeline smoke test,
not real telemetry or an attack against a target.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    token = os.environ.get('SOC_SOURCE_TOKEN')
    if not token:
        sys.exit('Set SOC_SOURCE_TOKEN to an authorized source token first.')
    base = os.environ.get('SOC_API_URL', 'http://localhost:8000').rstrip('/')
    scenario = str(uuid4())
    start = datetime.now(timezone.utc) - timedelta(seconds=90)
    events = [dict(external_event_id=f'{scenario}-{i}', event_time=(start + timedelta(seconds=i * 15)).isoformat(),
                   event_type='LOGIN_FAILED', source_ip='192.0.2.24', destination_ip='198.51.100.10', destination_port=22,
                   username='demo-admin', raw_data={'provenance': 'synthetic_pipeline_test', 'scenario': scenario}) for i in range(5)]
    request = Request(base + '/api/events/batch', data=json.dumps({'events': events}).encode(),
                      headers={'Content-Type': 'application/json', 'X-Source-Token': token})
    with urlopen(request, timeout=30) as response:
        print(response.read().decode())


if __name__ == '__main__':
    main()
