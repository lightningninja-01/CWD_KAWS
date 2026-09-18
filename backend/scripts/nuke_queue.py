import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import get_settings

async def clear_queue():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    
    res = await db.jobs.delete_many({"status": {"$in": ["queued", "running", "failed"]}})
    print(f"Nuked {res.deleted_count} pending rogue jobs from the queue!")

if __name__ == "__main__":
    asyncio.run(clear_queue())
