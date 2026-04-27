import asyncio
import hmac
import json
from datetime import timezone
from hashlib import sha256

import grpc
import httpx

from contracts import webhook_pb2, webhook_pb2_grpc
from webhook_service.core.logging.logging import *
from webhook_service.core.context.context import context_correlation_id


configure_logging("webhook_service")
logger = get_logger(__name__)


class WebhookSender(webhook_pb2_grpc.WebhookSenderServicer):
    async def SendWebhook(self, request: webhook_pb2.SendWebhookRequest, context):
        metadata = dict(context.invocation_metadata())
        token = context_correlation_id.set(metadata.get("x-correlation-id", "-"))

        try:
            if not request.target_url:
                logger.warning(
                    "Webhook delivery rejected because target_url is missing",
                    extra={
                        "event": "webhook_delivery_rejected",
                        "webhook_id": request.webhook_id,
                        "job_id": request.payload.job_id,
                        "grpc_method": "SendWebhook",
                    },
                )
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "target_url is required")

            logger.info(
                "Webhook delivery requested",
                extra={
                    "event": "webhook_delivery_requested",
                    "webhook_id": request.webhook_id,
                    "job_id": request.payload.job_id,
                    "target_url": request.target_url,
                    "grpc_method": "SendWebhook",
                },
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
                }
                body = json.dumps(safe_payload, separators=(",", ":")).encode()

                sign = hmac.new(
                    key=request.secret.encode(),
                    msg=body,
                    digestmod=sha256,
                ).hexdigest()

                delays = [0, 1, 2, 4]
                last_error = None
                success = False
                attempt_count = 0
                for attempt, delay in enumerate(delays, start=1):
                    attempt_count = attempt
                    if delay:
                        await asyncio.sleep(delay)

                    try:
                        resp = await client.post(
                            url=request.target_url,
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-Webhook-Signature": sign,
                                "X-Correlation-ID": context_correlation_id.get()
                            },
                            timeout=5.0,
                        )

                        if 200 <= resp.status_code < 300:
                            success = True
                            last_error = None
                            logger.info(
                                "Webhook delivery succeeded",
                                extra={
                                    "event": "webhook_delivery_succeeded",
                                    "webhook_id": request.webhook_id,
                                    "job_id": request.payload.job_id,
                                    "target_url": request.target_url,
                                    "status_code": resp.status_code,
                                    "attempt": attempt,
                                    "grpc_method": "SendWebhook",
                                },
                            )
                            break

                        if 500 <= resp.status_code < 600:
                            last_error = f"server error: {resp.status_code}"
                            logger.warning(
                                "Webhook delivery retryable failure",
                                extra={
                                    "event": "webhook_delivery_retryable_failure",
                                    "webhook_id": request.webhook_id,
                                    "job_id": request.payload.job_id,
                                    "target_url": request.target_url,
                                    "status_code": resp.status_code,
                                    "attempt": attempt,
                                    "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                                    "error_message": last_error,
                                    "grpc_method": "SendWebhook",
                                },
                            )
                            continue

                        if 400 <= resp.status_code < 500:
                            last_error = f"client error {resp.status_code}"
                            logger.warning(
                                "Webhook delivery failed",
                                extra={
                                    "event": "webhook_delivery_failed",
                                    "webhook_id": request.webhook_id,
                                    "job_id": request.payload.job_id,
                                    "target_url": request.target_url,
                                    "status_code": resp.status_code,
                                    "attempt": attempt,
                                    "error_message": last_error,
                                    "grpc_method": "SendWebhook",
                                },
                            )
                            break

                    except httpx.TimeoutException:
                        last_error = "timeout"
                        logger.warning(
                            "Webhook delivery retryable failure",
                            extra={
                                "event": "webhook_delivery_retryable_failure",
                                "webhook_id": request.webhook_id,
                                "job_id": request.payload.job_id,
                                "target_url": request.target_url,
                                "attempt": attempt,
                                "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                                "error_type": "TimeoutException",
                                "error_message": last_error,
                                "grpc_method": "SendWebhook",
                            },
                        )
                        continue
                    except httpx.RequestError as ex:
                        last_error = f"Request error: {str(ex)}"
                        logger.warning(
                            "Webhook delivery retryable failure",
                            extra={
                                "event": "webhook_delivery_retryable_failure",
                                "webhook_id": request.webhook_id,
                                "job_id": request.payload.job_id,
                                "target_url": request.target_url,
                                "attempt": attempt,
                                "retry_in_s": delays[attempt] if attempt < len(delays) else None,
                                "error_type": type(ex).__name__,
                                "error_message": last_error,
                                "grpc_method": "SendWebhook",
                            },
                        )
                        continue

            if not success:
                logger.warning(
                    "Webhook delivery finished with failure",
                    extra={
                        "event": "webhook_delivery_finished_with_failure",
                        "webhook_id": request.webhook_id,
                        "job_id": request.payload.job_id,
                        "target_url": request.target_url,
                        "attempt": attempt_count,
                        "error_message": last_error,
                        "grpc_method": "SendWebhook",
                    },
                )
        finally:
            context_correlation_id.reset(token)

        return webhook_pb2.SendWebhookResponse(
            webhook_id=request.webhook_id,
            status="sent" if success else "failed",
            error=last_error if last_error else "",
        )
        


async def serve():
    logger.info(
        "Starting webhook gRPC server",
        extra={
            "event": "grpc_server_starting",
            "grpc_method": "SendWebhook",
            "address": "[::]:2121",
        },
    )
    server = grpc.aio.server()
    webhook_pb2_grpc.add_WebhookSenderServicer_to_server(WebhookSender(), server)
    server.add_insecure_port("[::]:2121")
    await server.start()
    logger.info(
        "Webhook gRPC server started",
        extra={
            "event": "grpc_server_started",
            "grpc_method": "SendWebhook",
            "address": "[::]:2121",
        },
    )
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
