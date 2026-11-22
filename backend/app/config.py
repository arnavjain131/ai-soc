import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./soc.db')
    supabase_url: str = os.getenv('SUPABASE_URL', '').rstrip('/')
    supabase_key: str = os.getenv('SUPABASE_PUBLISHABLE_KEY', '')
    origins: str = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
    environment: str = os.getenv('APP_ENV', 'development')
    request_per_credential: int = int(os.getenv('SOC_REQUESTS_PER_CREDENTIAL_MINUTE', '120'))
    request_pool_per_minute: int = int(os.getenv('SOC_REQUEST_POOL_PER_MINUTE', '600'))
    request_burst: int = int(os.getenv('SOC_REQUEST_BURST', '30'))
    request_max_in_flight: int = int(os.getenv('SOC_REQUEST_MAX_IN_FLIGHT', '16'))

    def validate(self):
        if not (30 <= self.request_per_credential <= 6000
                and 60 <= self.request_pool_per_minute <= 60000
                and 1 <= self.request_burst <= 1000
                and 1 <= self.request_max_in_flight <= 64):
            raise ValueError('Request limit settings are outside their supported bounds')
        if self.environment == 'production':
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise ValueError('Production requires PostgreSQL with the psycopg driver')
            if not self.supabase_url.startswith('https://') or not self.supabase_key:
                raise ValueError('Production requires Supabase authentication configuration')
            if '*' in self.origins or any(not x.strip().startswith('https://') for x in self.origins.split(',')):
                raise ValueError('Production requires explicit HTTPS frontend origins')
