"""
Initialize SEB Default Presets
Run this script to create/update default SEB configuration presets
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import async_session_maker
from app.utils.seed_presets import seed_default_presets, check_presets_exist


async def main():
    print("=" * 60)
    print("SEB Preset Initialization Script")
    print("=" * 60)
    
    async with async_session_maker() as db:
        # Check current status
        print("\nChecking existing presets...")
        exists = await check_presets_exist(db)
        
        if exists:
            print("✓ All default presets already exist")
            response = input("\nDo you want to update them? (y/n): ")
            if response.lower() != 'y':
                print("Skipping update.")
                return
        
        # Seed/update presets
        print("\nSeeding default presets...")
        result = await seed_default_presets(db)
        
        print("\n" + "=" * 60)
        print("RESULTS:")
        print("=" * 60)
        print(f"Created: {len(result['created'])} presets")
        if result['created']:
            for preset in result['created']:
                print(f"  - {preset}")
        
        print(f"\nUpdated: {len(result['updated'])} presets")
        if result['updated']:
            for preset in result['updated']:
                print(f"  - {preset}")
        
        print(f"\nTotal presets: {result['total']}")
        print("\n✓ Preset initialization completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
