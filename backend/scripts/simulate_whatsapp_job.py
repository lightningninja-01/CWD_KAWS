import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import json
import os
import uuid

# Add the parent directory to sys.path so we can import 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import get_settings
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.tenant_repository import TenantRepository

async def run_simulation():
    print("Starting simulation...")
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    tenant_repo = TenantRepository(db)
    job_repo = JobRepository(db)
    
    # 1. Get or create a mock tenant
    tenant = await db.tenants.find_one({"phone_number_id": "mock_phone_id"})
    if not tenant:
        print("Creating mock tenant...")
        tenant_id = str(ObjectId())
        await db.tenants.insert_one({
            "_id": tenant_id,
            "id": tenant_id,
            "owner_email": "test@example.com",
            "phone_number_id": "mock_phone_id",
            "whatsapp_business_account_id": "mock_waba",
            "system_prompt": "You are a helpful AI assistant. Always respond concisely.",
            "is_active": True
        })
    else:
        tenant_id = str(tenant["_id"])
        
    print(f"Using Tenant ID: {tenant_id}")
    
    # 2. Construct a mock WhatsApp Webhook payload
    mock_message_id = f"wamid.{uuid.uuid4().hex}"
    customer_phone = "15551234567"
    
    mock_payload = {
        "inbound": {
            "from": customer_phone,
            "id": mock_message_id,
            "timestamp": "1700000000",
            "type": "text",
            "text": {"body": "Hello! What can you do for me?"}
        },
        "phone_number_id": "mock_phone_id"
    }
    
    # 3. Enqueue the job (JobWorker will pick this up automatically)
    print("Enqueueing simulated WhatsApp message job...")
    await job_repo.enqueue(
        job_type="webhook_message",
        payload=mock_payload,
        deduplication_key=f"whatsapp:{mock_message_id}"
    )
    
    print("Job successfully queued!")
    print("Check your backend terminal (running on localhost:5000) to see LangGraph process the message.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
