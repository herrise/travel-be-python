import os
import asyncpg
from fastapi import FastAPI, HTTPException
from typing import List, Tuple, Any, Optional, Union
from dotenv import load_dotenv
import logging
from contextlib import asynccontextmanager

# Load environment variables from .env file
load_dotenv()

# Read DB config from environment variables, with defaults
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", 5))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", 20))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", 60))
DB_COMMAND_TIMEOUT = int(os.getenv("DB_COMMAND_TIMEOUT", 30))

db_pool: Optional[asyncpg.pool.Pool] = None

def check_pool():
    """Check if database pool is available"""
    if db_pool is None:
        raise HTTPException(
            status_code=500, 
            detail="Database connection not available"
        )

async def connect_to_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            host=DB_HOST,
            port=DB_PORT,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            timeout=DB_POOL_TIMEOUT,
            command_timeout=DB_COMMAND_TIMEOUT,
            max_inactive_connection_lifetime=300,
        )
        logging.info("Database pool connected.")
        
        # Test the connection
        async with db_pool.acquire() as conn:
            await conn.fetchrow("SELECT 1")
        logging.info("Database connection test successful.")
        
    except Exception as e:
        logging.error(f"Failed to connect to database pool: {e}")
        db_pool = None
        raise

async def disconnect_from_db():
    global db_pool
    if db_pool:
        try:
            await db_pool.close()
            logging.info("Database pool closed.")
        except Exception as e:
            logging.error(f"Error closing database pool: {e}")
        finally:
            db_pool = None

async def fetch(query: str, *args) -> List[asyncpg.Record]:
    """Fetch multiple rows"""
    check_pool()
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetch(query, *args)
    except Exception as e:
        logging.error(f"Error executing fetch query: {e}")
        raise

async def fetchrow(query: str, *args) -> Optional[asyncpg.Record]:
    """Fetch a single row"""
    check_pool()
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    except Exception as e:
        logging.error(f"Error executing fetchrow query: {e}")
        raise

async def fetchval(query: str, *args) -> Optional[Any]:
    """Fetch a single value from the first row"""
    check_pool()
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    except Exception as e:
        logging.error(f"Error executing fetchval query: {e}")
        raise

async def execute(query: str, *args) -> str:
    """Execute a query and return the command status"""
    check_pool()
    try:
        async with db_pool.acquire() as conn:
            return await conn.execute(query, *args)
    except Exception as e:
        logging.error(f"Error executing query: {e}")
        raise

async def executemany(query: str, args_list: List[Tuple[Any]]) -> None:
    """Execute a query multiple times with different parameters"""
    check_pool()
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, args_list)
    except Exception as e:
        logging.error(f"Error executing executemany: {e}")
        raise

async def batch_insert(table: str, columns: List[str], values: List[Tuple[Any]]) -> None:
    """Batch insert multiple rows into a table"""
    if not values:
        return

    check_pool()
    
    if not table or not columns:
        raise ValueError("Table name and columns are required")
    
    # Sanitize table and column names (basic validation)
    if not table.replace('_', '').replace('-', '').isalnum():
        raise ValueError("Invalid table name")
    
    for col in columns:
        if not col.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f"Invalid column name: {col}")
    
    query = f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join(f"${i+1}" for i in range(len(columns)))})
    """

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, values)
    except Exception as e:
        logging.error(f"Error in batch insert: {e}")
        raise

async def batch_upsert(
    table: str, 
    columns: List[str], 
    values: List[Tuple[Any]], 
    conflict_columns: List[str],
    update_columns: Optional[List[str]] = None
) -> None:
    """Batch upsert (INSERT ... ON CONFLICT DO UPDATE)"""
    if not values:
        return

    check_pool()
    
    if not table or not columns or not conflict_columns:
        raise ValueError("Table name, columns, and conflict_columns are required")
    
    if update_columns is None:
        update_columns = [col for col in columns if col not in conflict_columns]
    
    conflict_clause = ", ".join(conflict_columns)
    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
    
    query = f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join(f"${i+1}" for i in range(len(columns)))})
        ON CONFLICT ({conflict_clause})
        DO UPDATE SET {update_clause}
    """

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, values)
    except Exception as e:
        logging.error(f"Error in batch upsert: {e}")
        raise

async def run_transaction(queries_with_params: List[Tuple[str, Tuple[Any]]]) -> List[Any]:
    """Run multiple queries in a single transaction and return results"""
    check_pool()
    results = []
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                for query, params in queries_with_params:
                    result = await conn.execute(query, *params)
                    results.append(result)
        return results
    except Exception as e:
        logging.error(f"Transaction failed, rolling back: {e}")
        raise

async def run_transaction_with_results(
    queries_with_params: List[Tuple[str, Tuple[Any], str]]
) -> List[Any]:
    """
    Run multiple queries in a transaction with different result types
    query_type can be: 'execute', 'fetch', 'fetchrow', 'fetchval'
    """
    check_pool()
    results = []
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                for query, params, query_type in queries_with_params:
                    if query_type == 'execute':
                        result = await conn.execute(query, *params)
                    elif query_type == 'fetch':
                        result = await conn.fetch(query, *params)
                    elif query_type == 'fetchrow':
                        result = await conn.fetchrow(query, *params)
                    elif query_type == 'fetchval':
                        result = await conn.fetchval(query, *params)
                    else:
                        raise ValueError(f"Invalid query type: {query_type}")
                    results.append(result)
        return results
    except Exception as e:
        logging.error(f"Transaction with results failed, rolling back: {e}")
        raise

# Modern FastAPI lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await connect_to_db()
        yield
    finally:
        # Shutdown
        await disconnect_from_db()

# Legacy event handlers
def init_db_events(app: FastAPI):
    @app.on_event("startup")
    async def startup():
        await connect_to_db()

    @app.on_event("shutdown")
    async def shutdown():
        await disconnect_from_db()

def get_pool_status() -> dict:
    """Get current pool status for monitoring"""
    if db_pool is None:
        return {"status": "disconnected", "size": 0, "free": 0}
    
    return {
        "status": "connected",
        "size": db_pool.get_size(),
        "free": db_pool.get_idle_size(),
        "max_size": db_pool.get_max_size(),
        "min_size": db_pool.get_min_size()
    }

# Health check function
async def health_check() -> bool:
    """Check if database is healthy"""
    try:
        check_pool()
        result = await fetchval("SELECT 1")
        return result == 1
    except Exception as e:
        logging.error(f"Database health check failed: {e}")
        return False



