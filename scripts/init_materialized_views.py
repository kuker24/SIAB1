import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add parent dir to path (ujian_online/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

async def init_views():
    print(f"Connecting to DB: {settings.database_url.split('@')[-1]}") # Log host only
    engine = create_async_engine(settings.database_url)
    
    sql_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app/migrations/create_materialized_views.sql"
    )
    
    if not os.path.exists(sql_path):
        print(f"Error: SQL file not found at {sql_path}")
        return

    with open(sql_path, "r") as f:
        sql_content = f.read()
    
    print("Creating Materialized Views...")
    try:
        async with engine.begin() as conn:
            # Simple split by ; works for this specific SQL file
            statements = sql_content.split(";")
            for stmt in statements:
                if stmt.strip():
                    await conn.execute(text(stmt))
                    print(f"Executed: {stmt.strip()[:50]}...")
        print("✅ Success! Materialized Views created.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_views())
