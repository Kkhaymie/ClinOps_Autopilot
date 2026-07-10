# backend/database/client.py
"""
Supabase client singleton.

Every other data-access module (`database.queries`, `intelligence.pattern_detector`,
etc.) imports `supabase` from here, so this file must expose a ready-to-use
client as soon as it is imported. Credentials come from the environment
(loaded via `.env` through python-dotenv in main.py, but we also call
load_dotenv() here so this module works if imported standalone, e.g. in tests).
"""

import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")

# Prefer the service-role key for backend use (bypasses RLS for trusted
# server-side operations); fall back to the anon key if that's all that's
# configured, so local/dev setups with only SUPABASE_KEY still work.
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Missing Supabase credentials. Set SUPABASE_URL and "
        "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) in backend/.env"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)