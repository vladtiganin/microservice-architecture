from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from main_service.api import dependencies
from main_service.main import app
from main_service.schemas.enums import JobStatus


@pytest.mark.asyncio
async def test_root_returns_status_ok(simple_async_client):
    response = await simple_async_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_jobs_returns_200_and_items(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.get_jobs = AsyncMock(
        return_value={
            "items": [
                {
                    "id": 1,
                    "type": "1",
                    "status": "pending",
                    "payload": "1",
                    "result": None,
                    "error": None,
                    "created_at": "2026-04-04T10:00:00",
                    "updated_at": None,
                    "started_at": None,
                    "finished_at": None,
                },
                {
                    "id": 2,
                    "type": "2",
                    "status": "pending",
                    "payload": "2",
                    "result": None,
                    "error": None,
                    "created_at": "2026-04-04T10:00:00",
                    "updated_at": None,
                    "started_at": None,
                    "finished_at": None,
                },
            ]
        }
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 1,
                "type": "1",
                "status": "pending",
                "payload": "1",
                "result": None,
                "error": None,
                "created_at": "2026-04-04T10:00:00",
                "updated_at": None,
                "started_at": None,
                "finished_at": None,
            },
            {
                "id": 2,
                "type": "2",
                "status": "pending",
                "payload": "2",
                "result": None,
                "error": None,
                "created_at": "2026-04-04T10:00:00",
                "updated_at": None,
                "started_at": None,
                "finished_at": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_get_jobs_passes_skip_and_limit_to_service(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.get_jobs = AsyncMock(return_value={"items": []})
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs?skip=5&limit=20")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    service_mock.get_jobs.assert_awaited_once_with(skip=5, limit=20, session=ANY)


@pytest.mark.asyncio
async def test_get_jobs_returns_200_and_empty_items(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.get_jobs = AsyncMock(return_value={"items": []})
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.asyncio
async def test_post_jobs_returns_200_and_create_job_response(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.create_job = AsyncMock(return_value=SimpleNamespace(id=9))
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.post("/jobs", json={"type": "email", "payload": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 9,
        "message": "To track job GET it by id",
    }

    call_kwargs = service_mock.create_job.await_args.kwargs
    assert call_kwargs["job"].type == "email"
    assert call_kwargs["job"].payload == "hello"
    assert call_kwargs["session"] is not None


@pytest.mark.asyncio
async def test_post_jobs_returns_422_when_type_is_missing(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.post("/jobs", json={"payload": "hello"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_jobs_returns_422_when_payload_is_missing(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.post("/jobs", json={"type": "email"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_jobs_returns_500_when_service_raises_http_exception(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.create_job = AsyncMock(
        side_effect=HTTPException(status_code=500, detail="Error during creating a job")
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.post("/jobs", json={"type": "email", "payload": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_job_by_id_returns_200_when_job_exists(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.get_job_by_id = AsyncMock(
        return_value={
            "id": 1,
            "type": "1",
            "status": "pending",
            "payload": "1",
            "result": None,
            "error": None,
            "created_at": "2026-04-04T10:00:00",
            "updated_at": None,
            "started_at": None,
            "finished_at": None,
        }
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs/1")
    finally:
        app.dependency_overrides.clear()

    service_mock.get_job_by_id.assert_awaited_once_with(job_id=1, session=ANY)
    assert response.status_code == 200
    assert response.json()["id"] == 1


@pytest.mark.asyncio
async def test_get_job_by_id_returns_404_when_job_does_not_exist(simple_async_client: httpx.AsyncClient):
    service_mock = Mock()
    service_mock.get_job_by_id = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Job with this id not found")
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs/1")
    finally:
        app.dependency_overrides.clear()

    service_mock.get_job_by_id.assert_awaited_once_with(job_id=1, session=ANY)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_by_id_returns_422_for_invalid_job_id(simple_async_client: httpx.AsyncClient):
    response = await simple_async_client.get("/jobs/abc")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_job_status_returns_job_status_payload(simple_async_client: httpx.AsyncClient):
    updated_at = datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc)
    service_mock = Mock()
    service_mock.get_job_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id=7,
            status=JobStatus.RUNNING,
            updated_at=updated_at,
        )
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs/7/status")
    finally:
        app.dependency_overrides.clear()

    service_mock.get_job_by_id.assert_awaited_once_with(7, ANY)
    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "status": "running",
        "updated_at": "2026-04-13T11:00:00Z",
    }


@pytest.mark.asyncio
async def test_get_job_status_returns_404_when_job_is_missing(
    simple_async_client: httpx.AsyncClient,
):
    service_mock = Mock()
    service_mock.get_job_by_id = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Job with this id not found")
    )
    app.dependency_overrides[dependencies.create_job_service_instance] = lambda: service_mock

    try:
        response = await simple_async_client.get("/jobs/7/status")
    finally:
        app.dependency_overrides.clear()

    service_mock.get_job_by_id.assert_awaited_once_with(7, ANY)
    assert response.status_code == 404
