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

    def validate(self):
        if self.environment == 'production':
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise ValueError('Production requires PostgreSQL with the psycopg driver')
            if not self.supabase_url.startswith('https://') or not self.supabase_key:
                raise ValueError('Production requires Supabase authentication configuration')
            if '*' in self.origins or any(not x.strip().startswith('https://') for x in self.origins.split(',')):
                raise ValueError('Production requires explicit HTTPS frontend origins')
