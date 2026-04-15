from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from main_service.api import jobs_api
from main_service.api import webhook_api

app = FastAPI(
    title="Job Processing Platform",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(jobs_api.router)
app.include_router(webhook_api.router)

@app.get("/")
def root():
    return {"status" : "ok"}


