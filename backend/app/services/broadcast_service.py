"""
Broadcast service — resolves a customer cohort by tags and fans out a
Meta-approved template message to each, used by the dashboard's Broadcast
Campaign Drawer.
"""
import asyncio

from app.database.repositories.customer_repository import CustomerRepository
from app.database.repositories.tenant_repository import TenantRepository
from app.exceptions.custom_exceptions import MetaAPIError
from app.schemas.broadcast_schema import BroadcastRequest, BroadcastResult
from app.services.whatsapp_client import WhatsAppClient
from app.utils.logger import get_logger

log = get_logger(__name__)

# Cap concurrent sends so we don't hammer the Graph API and trip rate limits.
_MAX_CONCURRENT_SENDS = 10


class BroadcastService:
    def __init__(
        self, customer_repo: CustomerRepository, whatsapp_client: WhatsAppClient,
        tenant_repo: TenantRepository | None = None,
    ) -> None:
        self._customer_repo = customer_repo
        self._whatsapp_client = whatsapp_client
        self._tenant_repo = tenant_repo

    async def send_broadcast(self, request: BroadcastRequest) -> BroadcastResult:
        tenant = await self._tenant_repo.get_by_id(request.tenant_id) if self._tenant_repo else None
        phone_number_id = tenant.phone_number_id if tenant else None
        resolved_customers = []
        tags_to_query = []

        for tag in request.target_tags:
            clean_tag = tag.strip()
            # Normalize by extracting digits only
            digits_only = "".join(c for c in clean_tag if c.isdigit())
            # Treat as phone number if it contains at least 7 digits and is mostly numeric
            if len(digits_only) >= 7 and len(digits_only) >= (len(clean_tag) * 0.7):
                customer = await self._customer_repo.get_or_create(request.tenant_id, digits_only)
                resolved_customers.append(customer)
            else:
                tags_to_query.append(clean_tag)

        if tags_to_query:
            tagged_customers = await self._customer_repo.find_by_tags(request.tenant_id, tags_to_query)
            existing_phones = {c.phone_number for c in resolved_customers}
            for c in tagged_customers:
                if c.phone_number not in existing_phones:
                    resolved_customers.append(c)
                    existing_phones.add(c.phone_number)

        customers = resolved_customers
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SENDS)
        failed_numbers: list[str] = []

        async def _send_one(phone: str) -> bool:
            async with semaphore:
                try:
                    await self._whatsapp_client.send_template(
                        phone, request.template_name, request.template_params, phone_number_id=phone_number_id
                    )
                    return True
                except MetaAPIError as exc:
                    log.warning(f"Broadcast send failed for {phone}: {exc.message} - Body: {exc.response_body}")
                    failed_numbers.append(phone)
                    return False
                except Exception as exc:  # noqa: BLE001 — one failed send shouldn't abort the batch
                    log.warning(f"Broadcast send failed for {phone}: {exc!r}")
                    failed_numbers.append(phone)
                    return False

        results = await asyncio.gather(*(_send_one(c.phone_number) for c in customers))
        total_sent = sum(1 for r in results if r)

        log.info(f"Broadcast complete: {total_sent}/{len(customers)} sent")
        return BroadcastResult(
            tenant_id=request.tenant_id,
            total_targeted=len(customers),
            total_sent=total_sent,
            total_failed=len(failed_numbers),
            failed_numbers=failed_numbers,
        )
