"""Email tool used by the support-refund agent.

This is the implementation behind the `send_email` tool exposed to the agent.
It is included in the repository because remediation for some failure patterns
lands in tool code rather than in agent configuration.
"""
import uuid
from typing import Any

from services.mailer import Mailer

mailer = Mailer()

DELIVERY_TIMEOUT_S = 10.0


def send_email(customer_id: str, template: str, order_id: str) -> dict[str, Any]:
    """Send a templated email to the customer.

    Raises TimeoutError if the upstream mailer does not acknowledge within
    DELIVERY_TIMEOUT_S. Note that a timeout does not mean the message was not
    delivered — the mailer may have accepted it and failed to respond in time.
    """
    message_id = str(uuid.uuid4())
    mailer.deliver(
        message_id=message_id,
        customer_id=customer_id,
        template=template,
        context={"order_id": order_id},
        timeout=DELIVERY_TIMEOUT_S,
    )
    return {"message_id": message_id, "delivered": True}
