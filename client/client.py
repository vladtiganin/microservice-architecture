import asyncio

import httpx

from enums import *


limits = httpx.Limits(keepalive_expiry=2.0)


class Client:
    def __init__(self, url: str):
        self.url = url

    @staticmethod
    def _parse_sse_message(message: str) -> dict[str, str] | None:
        if not message.strip():
            return None

        if message.startswith(":"):
            return None

        parsed: dict[str, str] = {}
        data_lines: list[str] = []

        for line in message.splitlines():
            if not line:
                continue

            if line.startswith(":"):
                return None

            field, _, value = line.partition(":")
            value = value.lstrip()

            if field == "data":
                data_lines.append(value)
            else:
                parsed[field] = value

        if data_lines:
            parsed["data"] = "\n".join(data_lines)

        return parsed if parsed else None


    async def create_job(self, type: str, payload: str) -> int:
        data = {
            "type": type,
            "payload": payload,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url=f"{self.url}/jobs",
                json=data,
            )
            resp.raise_for_status()
            print(f'Job id: {resp.json()["id"]}\nMessage: {resp.json()["message"]}')

        return resp.json()["id"]


    async def poll(self, job_id: int, poll_interval: int) -> None:
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
                    print("==================================")

                    if data["sequence_no"] > curr_seque:
                        curr_seque = data["sequence_no"]

                if body:
                    if body[-1]["event_type"] == JobEventType.FINISHED or body[-1]["event_type"] == JobEventType.FAILED:
                        return

                await asyncio.sleep(poll_interval)


    async def event_sse(self, job_id: int, event_sse_id: int = 0) -> int:
        async with httpx.AsyncClient(limits=limits) as client:
            async with client.stream(
                "GET",
                f"{self.url}/jobs/{job_id}/events/stream",
                headers={"last-event-id": str(event_sse_id)},
            ) as resp:
                resp.raise_for_status()
                buffer = ""

                async for chunk in resp.aiter_text():
                    buffer += chunk

                    while "\n\n" in buffer:
                        raw_event, buffer = buffer.split("\n\n", 1)
                        parsed_event = self._parse_sse_message(raw_event)

                        if parsed_event is None:
                            continue

                        if "id" in parsed_event:
                            event_sse_id = int(parsed_event["id"])

                        print(raw_event)
                        print()

        return event_sse_id


async def main():
    client = Client(url="http://127.0.0.1:8000")
    job_id = await client.create_job(type="sse", payload="client")
    last_id = await client.event_sse(job_id=job_id, event_sse_id=2)


if __name__ == "__main__":
    asyncio.run(main())
