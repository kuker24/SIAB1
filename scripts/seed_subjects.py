import asyncio
import sys
import os

# Add parent dir to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker
from app.api.subjects import seed_default_subjects
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting manual subject seeding...")
    async with async_session_maker() as db:
        try:
            await seed_default_subjects(db)
            logger.info("Seeding completed successfully!")
        except Exception as e:
            logger.error(f"Seeding failed: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(main())
