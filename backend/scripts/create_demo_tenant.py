import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import get_settings

async def create_tenant():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    
    tenant_data = {
        "id": "demo_tenant",
        "owner_email": "demo@example.com",
        "phone_number_id": "demo_phone",
        "whatsapp_business_account_id": "demo_waba",
        "system_prompt": "You are the WAAS agent. You help manage the user's schedule and emails.",
        "is_active": True
    }
    
    await db.tenants.update_one(
        {"_id": "demo_tenant"},
        {"$set": tenant_data},
        upsert=True
    )
    print("Successfully created demo_tenant!")

if __name__ == "__main__":
    asyncio.run(create_tenant())
