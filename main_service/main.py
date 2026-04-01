from fastapi import FastAPI
from api import jobs_api

app = FastAPI(
    title="Job Processing Platform",
    version="1.0.0"
)
app.include_router(jobs_api.router)

@app.get("/")
def root():
    return {"status" : "ok"}