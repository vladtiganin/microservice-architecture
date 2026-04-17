from contracts import webhook_pb2, webhook_pb2_grpc

import httpx
from datetime import datetime, timezone
import json
import hmac
from hashlib import sha256
import asyncio
import grpc
import logging
from pathlib import Path


LOG_PATH = Path(__file__).with_name("webhook_service.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class WebhookSender(webhook_pb2_grpc.WebhookSenderServicer):
    async def SendWebhook(self, request: webhook_pb2.SendWebhookRequest, context):
        if not request.target_url:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "target_url is required")

        logger.info(
            "SendWebhook called: webhook_id=%s target_url=%s job_id=%s",
            request.webhook_id,
            request.target_url,
            request.payload.job_id,
        )

        async with httpx.AsyncClient() as client:
            finished_at_iso = None
            if request.payload.HasField("finished_at"):
                finished_at_iso = (
                request.payload.finished_at
                .ToDatetime(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )

            safe_payload = {
                "job_id": request.payload.job_id,
                "status": request.payload.job_status,
                "finished_at": finished_at_iso,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }
            body = json.dumps(safe_payload, separators=(",", ":")).encode()

            sign = hmac.new(
                key=request.secret.encode(),
                msg=body,
                digestmod=sha256
            ).hexdigest()

            delays = [0, 1, 2, 4]
            last_error = None
            success = False
            for delay in delays:
                if delay:
                    await asyncio.sleep(delay)

                try:
                    resp = await client.post(
                        url=request.target_url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Webhook-Signature": sign,
                        },
                        timeout=5.0,
                    )

                    if 200 <= resp.status_code < 300:
                        success =  True
                        logger.info(
                            "Webhook delivered successfully: webhook_id=%s status_code=%s",
                            request.webhook_id,
                            resp.status_code,
                        )
                        break
                    
                    if 500 <= resp.status_code < 600:
                        last_error = f"server error: {resp.status_code}"
                        logger.warning(
                            "Webhook delivery retryable failure: webhook_id=%s error=%s",
                            request.webhook_id,
                            last_error,
                        )
                        continue

                    if 400 <= resp.status_code < 500:
                        last_error = f"client error {resp.status_code}: {resp.text}"
                        logger.warning(
                            "Webhook delivery failed: webhook_id=%s error=%s",
                            request.webhook_id,
                            last_error,
                        )
                        break


                except httpx.TimeoutException:
                    last_error = "timeout"
                    logger.warning(
                        "Webhook delivery timeout: webhook_id=%s",
                        request.webhook_id,
                    )
                    continue
                except httpx.RequestError as ex:
                    last_error = f"Request error: {str(ex)}"
                    logger.warning(
                        "Webhook delivery request error: webhook_id=%s error=%s",
                        request.webhook_id,
                        last_error,
                    )
                    continue

        if not success:
            logger.warning(
                "Webhook delivery finished with failure: webhook_id=%s error=%s",
                request.webhook_id,
                last_error,
            )

        return webhook_pb2.SendWebhookResponse(
            webhook_id=request.webhook_id,
            status= "sent" if success else "failed",
            error=last_error if last_error else ""
        )




async def serve():
    logger.info("Starting webhook gRPC server on [::]:2121")
    server = grpc.aio.server()
    webhook_pb2_grpc.add_WebhookSenderServicer_to_server(WebhookSender(), server)
    server.add_insecure_port("[::]:2121")
    await server.start()
    logger.info("Webhook gRPC server started")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
