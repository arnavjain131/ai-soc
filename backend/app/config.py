import os
from dataclasses import dataclass, field

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
    ai_enabled: bool = os.getenv('SOC_AI_ENABLED', 'false').lower() == 'true'
    openai_api_key: str = field(default=os.getenv('OPENAI_API_KEY', '').strip(), repr=False)
    ai_model: str = os.getenv('SOC_AI_MODEL', 'gpt-5.4-mini-2026-03-17')
    ai_daily_limit: int = int(os.getenv('SOC_AI_DAILY_LIMIT', '3'))
    ai_monthly_limit: int = int(os.getenv('SOC_AI_MONTHLY_LIMIT', '30'))
    ai_output_tokens: int = int(os.getenv('SOC_AI_MAX_OUTPUT_TOKENS', '2000'))

    def validate(self):
        if self.ai_model not in ('gpt-5.4-mini', 'gpt-5.4-mini-2026-03-17'):
            raise ValueError('Unsupported AI model; review model compatibility and costs before changing it')
        if not (1 <= self.ai_daily_limit <= 100 and 1 <= self.ai_monthly_limit <= 1000
                and 1000 <= self.ai_output_tokens <= 4000):
            raise ValueError('AI limits are outside their supported bounds')
        if self.ai_enabled and not self.openai_api_key:
            raise ValueError('Enabled AI requires a private server-side OPENAI_API_KEY')
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
