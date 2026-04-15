from contracts import executor_pb2, executor_pb2_grpc
import asyncio
import grpc.aio
import grpc

class Executor(executor_pb2_grpc.ExecutorServicer):
    async def ExecuteJob(self, request: executor_pb2.ExecuteJobRequest, context):
        if request.job_id == 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id required")

        if not request.type:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_type required")

        try:
            await asyncio.sleep(1)
            yield executor_pb2.ExecuteJobResponse(
                progres=10,
                status="running",
            )

            await asyncio.sleep(1)
            yield executor_pb2.ExecuteJobResponse(
                progres=30,
                status="running",
            )

            await asyncio.sleep(1)
            yield executor_pb2.ExecuteJobResponse(
                progres=50,
                status="running",
            )

            await asyncio.sleep(1)
            yield executor_pb2.ExecuteJobResponse(
                progres=90,
                status="running",
            )

            await asyncio.sleep(1)
            yield executor_pb2.ExecuteJobResponse(
                progres=100,
                status="finished",
            )
        except Exception as ex:
            yield executor_pb2.ExecuteJobResponse(
                error="Somethin goes wrong during executing",
                status="failed"
            )



async def serve():
    server = grpc.aio.server()
    executor_pb2_grpc.add_ExecutorServicer_to_server(Executor(), server)
    server.add_insecure_port("[::]:4343")
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.create_task(serve)