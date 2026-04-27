import asyncio

import grpc
import grpc.aio

from contracts import executor_pb2, executor_pb2_grpc
from executor_service.core.logging import *
from executor_service.core.context import context_correlation_id



configure_logging("executor_service")
logger = get_logger(__name__)


class Executor(executor_pb2_grpc.ExecutorServicer):
    async def ExecuteJob(self, request: executor_pb2.ExecuteJobRequest, context):
        metadata = dict(context.invocation_metadata())
        token = context_correlation_id.set(metadata.get("x-correlation-id", "-"))

        try:
            logger.info(
                "Job execution request received",
                extra={
                    "event": "job_execution_request_received",
                    "job_id": request.job_id,
                    "job_type": request.type or None,
                    "grpc_method": "ExecuteJob",
                },
            )

            if request.job_id == 0:
                logger.warning(
                    "Job execution request rejected because job_id is missing",
                    extra={
                        "event": "job_execution_request_rejected",
                        "grpc_method": "ExecuteJob",
                    },
                )
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id required")

            if not request.type:
                logger.warning(
                    "Job execution request rejected because job_type is missing",
                    extra={
                        "event": "job_execution_request_rejected",
                        "job_id": request.job_id,
                        "grpc_method": "ExecuteJob",
                    },
                )
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_type required")

            logger.info(
                "Job execution started",
                extra={
                    "event": "job_execution_started",
                    "job_id": request.job_id,
                    "job_type": request.type,
                    "grpc_method": "ExecuteJob",
                },
            )

            try:
                await asyncio.sleep(1)
                yield executor_pb2.ExecuteJobResponse(
                    progress=10,
                    status="running",
                )

                await asyncio.sleep(1)
                yield executor_pb2.ExecuteJobResponse(
                    progress=30,
                    status="running",
                )

                await asyncio.sleep(1)
                yield executor_pb2.ExecuteJobResponse(
                    progress=50,
                    status="running",
                )

                await asyncio.sleep(1)
                yield executor_pb2.ExecuteJobResponse(
                    progress=90,
                    status="running",
                )

                await asyncio.sleep(1)
                logger.info(
                    "Job execution completed",
                    extra={
                        "event": "job_execution_completed",
                        "job_id": request.job_id,
                        "job_type": request.type,
                        "job_status": "finished",
                        "grpc_method": "ExecuteJob",
                    },
                )
                yield executor_pb2.ExecuteJobResponse(
                    progress=100,
                    status="finished",
                    result="job completed successfully",
                )
            except asyncio.CancelledError:
                logger.info(
                    "Job execution cancelled",
                    extra={
                        "event": "job_execution_cancelled",
                        "job_id": request.job_id,
                        "job_type": request.type,
                        "grpc_method": "ExecuteJob",
                    },
                )
                raise
            except Exception:
                logger.exception(
                    "Job execution failed",
                    extra={
                        "event": "job_execution_failed",
                        "job_id": request.job_id,
                        "job_type": request.type,
                        "grpc_method": "ExecuteJob",
                    },
                )
                if not context.cancelled():
                    yield executor_pb2.ExecuteJobResponse(
                        error="Something goes wrong during execution",
                        status="failed",
                    )
        finally:
            context_correlation_id.reset(token)


async def serve():
    logger.info(
        "Starting executor gRPC server",
        extra={
            "event": "grpc_server_starting",
            "grpc_method": "ExecuteJob",
            "address": "[::]:4343",
        },
    )
    server = grpc.aio.server()
    executor_pb2_grpc.add_ExecutorServicer_to_server(Executor(), server)
    server.add_insecure_port("[::]:4343")
    await server.start()
    logger.info(
        "Executor gRPC server started",
        extra={
            "event": "grpc_server_started",
            "grpc_method": "ExecuteJob",
            "address": "[::]:4343",
        },
    )
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
