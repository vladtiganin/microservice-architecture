# Job Processing Platform

Асинхронная backend-платформа для создания, выполнения и отслеживания фоновых задач. Проект построен как набор сервисов: HTTP orchestrator принимает запросы клиентов, worker выполняет задачи по gRPC, события сохраняются в PostgreSQL и доступны через polling или SSE.

## Описание проекта

Система решает задачу управляемого запуска долгих операций, когда клиенту не нужно держать HTTP-запрос открытым до завершения работы.

Основной сценарий:

1. Пользователь регистрируется и получает JWT access token.
2. Клиент создает задачу через HTTP API.
3. Главный сервис сохраняет задачу и события жизненного цикла в PostgreSQL.
4. Главный сервис запускает выполнение в отдельном executor-сервисе через gRPC server streaming.
5. Клиент отслеживает прогресс через polling или SSE.
6. Для внешних систем можно зарегистрировать webhook-подписку и доставлять terminal-события HTTP POST-запросом с HMAC-подписью.

Проект демонстрирует микросервисное взаимодействие, event-based модель состояния, асинхронный Python backend, gRPC contracts, PostgreSQL persistence и тестирование API, сервисов и репозиториев.

## Архитектура

Компоненты системы:

- `main_service` - главный HTTP orchestrator на FastAPI. Отвечает за аутентификацию, создание задач, хранение состояния, выдачу событий, SSE stream и управление webhook-подписками.
- `executor_service` - gRPC worker-сервис. Принимает `ExecuteJobRequest`, выполняет задачу и стримит прогресс обратно в orchestrator.
- `webhook_service` - gRPC сервис доставки webhook. Получает команду `SendWebhook`, формирует HTTP POST, подписывает payload и выполняет retry.
- `postgres_db` - основная PostgreSQL база для пользователей, задач, событий и webhook-подписок.
- `postgres_test` - отдельная PostgreSQL база для integration-тестов.
- `client` - пример асинхронного клиента для создания задач, polling, SSE и приема webhook.

Текстовый поток данных:

```text
HTTP client
  -> POST /jobs
  -> main_service сохраняет Job(status=pending) и JobEvent(created)
  -> main_service переводит Job в queued и пишет JobEvent(queued)
  -> main_service запускает background task
  -> gRPC Executor.ExecuteJob(...)
  -> executor_service stream-ит running/finished/failed
  -> main_service пишет новые JobEvent и обновляет Job
  -> клиент читает /jobs/{id}/events, /status или /events/stream
```

Webhook-поток:

```text
HTTP client
  -> POST /webhook
  -> main_service сохраняет WebhookSubscription(secret, target_url)
  -> main_service.dispatch_job_event(...)
  -> gRPC WebhookSender.SendWebhook(...)
  -> webhook_service отправляет подписанный HTTP POST во внешний target_url
```

Важно: в текущем gRPC lifecycle webhook dispatch реализован как сервисная операция, но не вызывается автоматически после terminal-события из `JobService._manage_job_executing`. Это честное ограничение текущей версии.

## Поддерживаемые способы взаимодействия

### HTTP API

Основные endpoints:

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| `GET` | `/` | Healthcheck, возвращает `{"status": "ok"}` |
| `POST` | `/auth/register` | Регистрация пользователя |
| `POST` | `/auth/login` | Получение JWT access token |
| `GET` | `/jobs` | Список задач с пагинацией `skip`, `limit` |
| `POST` | `/jobs` | Создание задачи, требует Bearer token |
| `GET` | `/jobs/{job_id}` | Полная информация о задаче |
| `GET` | `/jobs/{job_id}/status` | Текущий статус задачи |
| `GET` | `/jobs/{job_id}/events` | Список событий задачи |
| `GET` | `/jobs/{job_id}/events/stream` | SSE stream событий задачи |
| `POST` | `/webhook` | Создание webhook-подписки для задачи |
| `DELETE` | `/webhook/{webhook_id}` | Удаление webhook-подписки |

### Polling

Polling построен поверх event log:

- клиент вызывает `GET /jobs/{job_id}/events?skip=<last_sequence_no>&limit=<n>`;
- репозиторий возвращает события с `sequence_no > skip`;
- клиент сохраняет максимальный `sequence_no` и передает его в следующем запросе;
- terminal-события `finished` и `failed` означают, что задачу можно больше не опрашивать.

Начальное значение `skip` обычно равно `0`.

### SSE

SSE endpoint:

```http
GET /jobs/{job_id}/events/stream
Accept: text/event-stream
Last-Event-ID: 2
```

Особенности реализации:

- stream возвращается через `StreamingResponse`;
- заголовки ответа: `Cache-Control: no-cache`, `Connection: keep-alive`;
- при отсутствии новых событий сервис отправляет heartbeat `: ping`;
- reconnect поддерживается через header `Last-Event-ID`;
- stream закрывается после terminal-события `finished` или `failed`;
- надежнее читать тип события из JSON поля `data.event_type`, так как SSE `event:` сейчас формируется из Python enum representation.

Пример SSE-сообщения:

```text
id: 3
event: JobEventType.RUNNING
data: {"id":3,"job_id":7,"event_type":"running","sequence_no":3,"payload":{"progress":"10%"},"created_at":"2026-04-13T10:00:00"}
```

### WebSocket

WebSocket API в текущей версии не реализован. Для realtime-обновлений используется SSE.

### Webhook

Webhook-подписка создается для конкретной задачи:

- `POST /webhook` сохраняет `job_id`, `target_url`, `secret`, `is_active`;
- delivery payload подписывается HMAC-SHA256;
- подпись передается в заголовке `X-Webhook-Signature`;
- `webhook_service` повторяет доставку при timeout, network error и HTTP `5xx`;
- HTTP `4xx` считается неретраибельной ошибкой;
- результат доставки сохраняется в `delivery_status` и `error`.

Текущая политика retry:

```text
attempt delays: 0s, 1s, 2s, 4s
request timeout: 5s
```

Payload доставки:

```json
{
  "job_id": 7,
  "status": "succeeded",
  "finished_at": "2026-04-13T12:00:00Z"
}
```

### gRPC

Внутреннее взаимодействие между сервисами вынесено в protobuf contracts:

- `proto/executor.proto`
  - `Executor.ExecuteJob(ExecuteJobRequest) returns (stream ExecuteJobResponse)`
  - orchestrator получает progress stream и превращает его в `JobEvent`.
- `proto/webhook.proto`
  - `WebhookSender.SendWebhook(SendWebhookRequest) returns (SendWebhookResponse)`
  - webhook-сервис доставляет событие во внешний HTTP endpoint.

Correlation ID передается между сервисами через gRPC metadata `x-correlation-id`.

## Технологии

- Python 3.12 - основной язык сервисов, Docker images используют `python:3.12-slim`.
- FastAPI - HTTP API, dependency injection, response models, middleware.
- PostgreSQL 16 - основное хранилище данных.
- SQLAlchemy 2.x async ORM - модели, async session, репозитории.
- asyncpg / psycopg - драйверы PostgreSQL для приложения и миграций.
- Alembic - управление схемой базы данных.
- gRPC / protobuf - контракты и межсервисное взаимодействие.
- Docker / Docker Compose - контейнеризация сервисов и баз данных.
- Pydantic / pydantic-settings - схемы API и конфигурация из `.env`.
- python-jose - выпуск и проверка JWT.
- passlib + argon2 - хеширование паролей.
- httpx - async HTTP client для webhook delivery и тестовых клиентов.
- pytest / pytest-asyncio - unit, API и integration тесты.
- Structured JSON logging - единый формат логов с `service`, `event`, `correlation_id`.

## Модель данных

### User

Пользователь системы.

Основные поля:

- `id` - первичный ключ.
- `email` - уникальный email.
- `hashed_password` - пароль в хешированном виде.
- `created_at` - время регистрации.

### Job

Фоновая задача.

Основные поля:

- `id` - идентификатор задачи.
- `user_id` - владелец задачи.
- `type` - тип задачи, строка до 50 символов.
- `status` - текущий статус lifecycle.
- `correlation_id` - идентификатор трассировки запроса.
- `payload` - входные данные задачи в строковом виде.
- `result` - результат выполнения, если задача завершилась успешно.
- `error` - текст ошибки, если задача завершилась неуспешно.
- `created_at` - время создания.
- `updated_at` - время последнего обновления.
- `started_at` - время первого перехода в `running`.
- `finished_at` - время перехода в terminal-статус.

Для ускорения выборок есть индекс по `status`.

### JobEvent

Append-only событие жизненного цикла задачи.

Основные поля:

- `id` - идентификатор события.
- `job_id` - задача, к которой относится событие.
- `event_type` - тип события: `created`, `queued`, `started`, `running`, `finished`, `failed`.
- `sequence_no` - порядковый номер события внутри задачи.
- `payload` - JSON с деталями события, например progress.
- `created_at` - время создания события.

Для одной задачи пара `(job_id, sequence_no)` уникальна. Это основа polling и SSE reconnect.

### WebhookSubscription

Подписка внешней системы на событие задачи.

Основные поля:

- `id` - идентификатор подписки.
- `job_id` - задача, к которой привязан webhook.
- `target_url` - внешний URL получателя.
- `secret` - секрет для HMAC-подписи.
- `is_active` - активность подписки.
- `created_at` - время создания.
- `delivery_status` - последний результат доставки: `sent` или `failed`.
- `error` - последняя ошибка доставки.

## Жизненный цикл задачи

Поддерживаемые статусы:

- `pending` - задача создана в БД.
- `queued` - задача поставлена на выполнение.
- `running` - executor прислал progress-событие.
- `succeeded` - executor завершил задачу статусом `finished`.
- `failed` - executor прислал `failed`, gRPC вызов упал или пришел неизвестный статус.
- `cancelled` - статус есть в enum, но cancel-flow и HTTP endpoint отмены пока не реализованы.

Типичный переход:

```text
pending -> queued -> running -> succeeded
                         \
                          -> failed
```

Генерируемые события:

- `created` - после сохранения `Job`.
- `queued` - после постановки задачи в очередь выполнения.
- `running` - при каждом progress-сообщении от executor.
- `finished` - при успешном завершении.
- `failed` - при ошибке выполнения или инфраструктурной ошибке.
- `started` - поддерживается enum и legacy executor-кодом, но текущий gRPC executor начинает поток с `running`.

## Примеры API

### Регистрация и login

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"strong-password"}'
```

```json
{
  "status": "success",
  "message": "User successfully registraited"
}
```

Login использует OAuth2 form body:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=strong-password"
```

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

### Создание задачи

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"type":"email","payload":"hello"}'
```

Ответ:

```json
{
  "id": 7,
  "message": "To track job GET it by id"
}
```

### Получение задачи

```bash
curl http://localhost:8000/jobs/7
```

```json
{
  "id": 7,
  "type": "email",
  "status": "running",
  "payload": "hello",
  "result": null,
  "error": null,
  "created_at": "2026-04-13T09:59:55Z",
  "updated_at": "2026-04-13T10:00:01Z",
  "started_at": "2026-04-13T10:00:00Z",
  "finished_at": null
}
```

### Получение статуса

```bash
curl http://localhost:8000/jobs/7/status
```

```json
{
  "id": 7,
  "status": "running",
  "updated_at": "2026-04-13T10:00:01Z"
}
```

### Получение событий

```bash
curl "http://localhost:8000/jobs/7/events?skip=0&limit=10"
```

```json
{
  "items": [
    {
      "id": 1,
      "job_id": 7,
      "event_type": "created",
      "sequence_no": 1,
      "payload": {
        "type": "email"
      },
      "created_at": "2026-04-13T09:59:55Z"
    },
    {
      "id": 2,
      "job_id": 7,
      "event_type": "queued",
      "sequence_no": 2,
      "payload": {
        "time": "2026-04-13T09:59:55.200000"
      },
      "created_at": "2026-04-13T09:59:55Z"
    }
  ]
}
```

### SSE stream

```bash
curl -N http://localhost:8000/jobs/7/events/stream \
  -H "Last-Event-ID: 2"
```

Пример фрагмента stream:

```text
: ping

id: 3
event: JobEventType.RUNNING
data: {"id":3,"job_id":7,"event_type":"running","sequence_no":3,"payload":{"progress":"10%"},"created_at":"2026-04-13T10:00:00"}
```

### Webhook-подписка

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"job_id":7,"target_url":"https://example.com/hooks/job"}'
```

```json
{
  "id": 3,
  "job_id": 7,
  "target_url": "https://example.com/hooks/job",
  "secret": "<generated-secret>",
  "created_at": "2026-04-13T10:00:00Z"
}
```

## Запуск проекта

### Через Docker

Подготовьте `main_service/.env` для запуска внутри Docker network:

```env
db_dns=postgresql+asyncpg://postgres:postgres@postgres_db:5432/db
executor_service_address=executor_service:4343
webhook_service_address=webhook_service:2121
jwt_secret_key=change-me
```

Поднять инфраструктуру и сервисы:

```bash
docker compose up -d --build
```

Сервисы:

- `main_service` - HTTP API на `http://localhost:8000`.
- `executor_service` - gRPC worker на `localhost:4343`.
- `webhook_service` - gRPC webhook sender на `localhost:2121`.
- `postgres_db` - PostgreSQL на `localhost:5434`.
- `postgres_test` - тестовая PostgreSQL на `localhost:5433`.

Миграции не запускаются автоматически контейнером. После старта PostgreSQL примените их с хоста:

```bash
alembic upgrade head
```

Если Alembic установлен только в локальном venv на Windows:

```powershell
.\venv\Scripts\alembic.exe upgrade head
```

### Локально

Создать и активировать виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Для Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Подготовить `main_service/.env` для локального запуска:

```env
db_dns=postgresql+asyncpg://postgres:postgres@localhost:5434/db
executor_service_address=localhost:4343
webhook_service_address=localhost:2121
jwt_secret_key=change-me
```

Поднять PostgreSQL:

```bash
docker compose up -d postgres_db
alembic upgrade head
```

Запустить сервисы в отдельных терминалах:

```bash
python -m executor_service.executor
```

```bash
python -m webhook_service.webhook
```

```bash
uvicorn main_service.main:app --host 0.0.0.0 --port 8000 --reload
```

Проверка:

```bash
curl http://localhost:8000/
```

## Тестирование

Быстрый набор unit и API тестов:

```powershell
.\venv\Scripts\python.exe -m pytest tests\unit tests\api -q
```

Полный набор тестов:

```powershell
docker compose up -d postgres_test
.\venv\Scripts\python.exe -m pytest -q
```

Для Linux/macOS после активации venv:

```bash
pytest tests/unit tests/api -q
pytest -q
```

Типы тестов:

- `tests/unit` - сервисная логика, gRPC handlers, retry webhook, transition logic, structured logging.
- `tests/api` - FastAPI endpoints через `httpx.ASGITransport`.
- `tests/integration` - репозитории и lifecycle поверх PostgreSQL test database.

Integration-тесты используют `TEST_DATABASE_URL`. Значение по умолчанию:

```env
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/jobs_test
```

Если тестовая БД недоступна, integration fixtures пропускают соответствующие тесты.

## Особенности реализации

- Event-based модель: состояние задачи не только хранится в `jobs.status`, но и фиксируется в `job_events`.
- Последовательность событий: `sequence_no` дает простой механизм polling, replay и SSE reconnect.
- SSE streaming: один endpoint покрывает realtime-обновления без WebSocket.
- gRPC server streaming: executor отправляет прогресс по мере выполнения задачи.
- Webhook retry: доставка повторяется при временных ошибках, timeout и HTTP `5xx`.
- HMAC-подпись webhook: получатель может проверить, что payload был отправлен системой.
- Correlation ID: HTTP middleware создает или принимает `X-Correlation-ID`, дальше он попадает в логи и gRPC metadata.
- Structured logging: сервисы пишут JSON-логи с полями `service`, `event`, `logger`, `correlation_id`.
- Ошибки приложения: доменные `AppException` преобразуются в единый JSON response через FastAPI exception handler.

## Ограничения и возможные улучшения

- WebSocket API отсутствует; realtime-поток реализован через SSE.
- Cancel endpoint не реализован, хотя статус `cancelled` есть в enum.
- Нет отдельного брокера очередей: выполнение запускается background task внутри `main_service`.
- In-flight задачи не восстанавливаются после рестарта `main_service`.
- Payload задачи хранится как строка, без типизированной схемы под разные `job.type`.
- Авторизация применена к созданию задач, но чтение задач, событий и webhook endpoints в текущей версии не проверяют владельца.
- Webhook dispatch реализован, но не подключен автоматически к текущему gRPC lifecycle после `finished` или `failed`.
- Docker Compose не применяет Alembic migrations автоматически.
- gRPC transport используется без TLS, что приемлемо только для локального/dev окружения или закрытой сети.
- SSE `event:` сейчас содержит Python enum representation; для клиентов стабильнее использовать `data.event_type`.
- Нет rate limiting, идемпотентных ключей и production-ready observability stack.

## Заключение

`Job Processing Platform` показывает практическую backend-архитектуру для асинхронных задач: FastAPI HTTP API, PostgreSQL persistence, SQLAlchemy async repositories, gRPC worker interaction, event log, SSE streaming, JWT authentication, webhook delivery и тестирование на нескольких уровнях.

Проект не маскирует ограничения, но содержит основу, которую можно развивать в сторону production-системы: добавить брокер очередей, автоматическую доставку terminal-webhook, cancel-flow, owner-based authorization и полноценный observability stack.
