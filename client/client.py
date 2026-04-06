import httpx
from enums import *
import asyncio

class Client:
    def __init__(self, url: str):
        self.url = url


    async def create_job(self, type: str, payload: str) -> int:
        data = {
            "type": type,
            "payload": payload
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url=f"{self.url}/jobs",
                json=data
            )
            resp.raise_for_status()
            print(f'Job id: {resp.json()["id"]}\nMessage: {resp.json()["message"]}')

        return resp.json()["id"]


    async def poll(self, job_id: int, poll_interval: int) -> None:
        limits = httpx.Limits(
            keepalive_expiry=2.0
        )

        curr_seque = 1
        async with httpx.AsyncClient(limits=limits) as client:
            while True:
                resp = await client.get(f"{self.url}/jobs/{job_id}/events?skip={curr_seque}&limit=20")
                resp.raise_for_status()
                body = resp.json()["items"]
                for data in body:
                    print(f'event id: {data["id"]}')
                    print(f'job id: {data["job_id"]}')
                    print(f'event type: {data["event_type"]}')
                    print(f'sequence number: {data["sequence_no"]}')
                    print(f'created at: {data["created_at"]}')
                    print('==================================')

                    if data['sequence_no'] > curr_seque:
                        curr_seque = data['sequence_no']

                if body:
                    if body[-1]["event_type"] == JobEventType.FINISHED or body[-1]["event_type"] == JobEventType.FAILED:
                        return
                
                await asyncio.sleep(poll_interval)


async def main():
    client = Client(url="http://127.0.0.1:8000")
    job_id = await client.create_job(type="type_3", payload="email")
    await client.poll(job_id, 1)


if __name__ == "__main__":
    asyncio.run(main())
