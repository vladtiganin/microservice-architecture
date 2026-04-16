from contracts import executor_pb2, executor_pb2_grpc
import asyncio
import logging
from pathlib import Path
import grpc.aio
import grpc


LOG_PATH = Path(__file__).with_name("executor_service.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

class Executor(executor_pb2_grpc.ExecutorServicer):
    async def ExecuteJob(self, request: executor_pb2.ExecuteJobRequest, context):
        logger.info(
            "ExecuteJob called: job_id=%s type=%s payload=%s",
            request.job_id,
            request.type,
            request.payload,
        )

        if request.job_id == 0:
            logger.warning("Rejecting request without job_id")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id required")

        if not request.type:
            logger.warning("Rejecting request without job_type for job_id=%s", request.job_id)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_type required")

        try:
            await asyncio.sleep(1)
            logger.info(
                "Sending progress update: job_id=%s progress=%s status=%s",
                request.job_id,
                10,
                "running",
            )
            yield executor_pb2.ExecuteJobResponse(
                progress=10,
                status="running",
            )

            await asyncio.sleep(1)
            logger.info(
                "Sending progress update: job_id=%s progress=%s status=%s",
                request.job_id,
                30,
                "running",
            )
            yield executor_pb2.ExecuteJobResponse(
                progress=30,
                status="running",
            )

            await asyncio.sleep(1)
            logger.info(
                "Sending progress update: job_id=%s progress=%s status=%s",
                request.job_id,
                50,
                "running",
            )
            yield executor_pb2.ExecuteJobResponse(
                progress=50,
                status="running",
            )

            await asyncio.sleep(1)
            logger.info(
                "Sending progress update: job_id=%s progress=%s status=%s",
                request.job_id,
                90,
                "running",
            )
            yield executor_pb2.ExecuteJobResponse(
                progress=90,
                status="running",
            )

            await asyncio.sleep(1)
            logger.info(
                "Sending progress update: job_id=%s progress=%s status=%s",
                request.job_id,
                100,
                "finished",
            )
            yield executor_pb2.ExecuteJobResponse(
                progress=100,
                status="finished",
                result="job completed successfully"
            )
        except asyncio.CancelledError:
             logger.info("RPC cancelled for job_id=%s", request.job_id)
             raise
        except Exception as ex:
            logger.exception("Execution failed for job_id=%s", request.job_id)
            if not context.cancelled():
                yield executor_pb2.ExecuteJobResponse(
                    error="Something goes wrong during execution",
                    status="failed"
                )



async def serve():
    logger.info("Starting executor gRPC server on [::]:4343")
    server = grpc.aio.server()
    executor_pb2_grpc.add_ExecutorServicer_to_server(Executor(), server)
    server.add_insecure_port("[::]:4343")
    await server.start()
    logger.info("Executor gRPC server started")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
