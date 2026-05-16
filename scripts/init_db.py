"""Initialize the database with TimescaleDB hypertables."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arb.infra.db import init_db

if __name__ == "__main__":
    asyncio.run(init_db())
    print("Database ready.")
