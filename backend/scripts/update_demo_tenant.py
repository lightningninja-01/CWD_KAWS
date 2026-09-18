import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import get_settings

async def update_tenant():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    
    await db.tenants.update_one(
        {"_id": "demo_tenant"},
        {"$set": {
            "company_name": "Demo Corp",
            "branding": {
                "display_name": "WAAS Demo",
                "primary_color": "#000000",
                "logo_url": ""
            }
        }}
    )
    print("Successfully updated demo_tenant with ALL missing fields!")

if __name__ == "__main__":
    asyncio.run(update_tenant())
