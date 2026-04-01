from fastapi import FastAPI

app = FastAPI(
    title="Job Processing Platform",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"status" : "ok"}