from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from arb.config import settings

# Engine is lazy — connection is only established when first query runs.
# The system boots fine without PostgreSQL; DB writes fail silently in feeds.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"timeout": 5},
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS ticks (
        time        TIMESTAMPTZ NOT NULL,
        symbol      TEXT        NOT NULL,
        exchange    TEXT        NOT NULL,
        bid         DOUBLE PRECISION,
        ask         DOUBLE PRECISION,
        mid         DOUBLE PRECISION
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS funding_rates (
        time        TIMESTAMPTZ NOT NULL,
        symbol      TEXT        NOT NULL,
        exchange    TEXT        NOT NULL,
        rate        DOUBLE PRECISION
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
        time        TIMESTAMPTZ NOT NULL,
        strategy    TEXT        NOT NULL,
        symbol      TEXT        NOT NULL,
        score       DOUBLE PRECISION,
        meta        JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        time        TIMESTAMPTZ NOT NULL,
        symbol      TEXT        NOT NULL,
        side        TEXT        NOT NULL,
        qty         DOUBLE PRECISION,
        price       DOUBLE PRECISION,
        pnl         DOUBLE PRECISION,
        strategy    TEXT,
        exchange    TEXT
    );
    """,
]

_HYPERTABLES = [
    "SELECT create_hypertable('ticks', by_range('time'), if_not_exists => TRUE);",
    "SELECT create_hypertable('funding_rates', by_range('time'), if_not_exists => TRUE);",
    "SELECT create_hypertable('signals', by_range('time'), if_not_exists => TRUE);",
    "SELECT create_hypertable('trades', by_range('time'), if_not_exists => TRUE);",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ticks_symbol ON ticks (symbol, exchange, time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals (strategy, time DESC);",
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol, time DESC);",
]


async def init_db() -> None:
    timescale_ok = False

    # Extension creation needs its own transaction; failure must not poison DDL.
    async with engine.begin() as conn:
        try:
            await conn.execute(text(_CREATE_EXTENSION))
            timescale_ok = True
        except Exception as e:
            print(f"[db] TimescaleDB not available ({type(e).__name__}); using plain tables.")

    # Tables + indexes in a separate transaction.
    async with engine.begin() as conn:
        for stmt in _DDL:
            await conn.execute(text(stmt))
        for stmt in _INDEXES:
            await conn.execute(text(stmt))

    # Hypertables (no-op if extension absent).
    if timescale_ok:
        async with engine.begin() as conn:
            for stmt in _HYPERTABLES:
                try:
                    await conn.execute(text(stmt))
                except Exception:
                    pass

    mode = "TimescaleDB hypertables" if timescale_ok else "plain PostgreSQL tables"
    print(f"Database initialized with {mode}.")


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
