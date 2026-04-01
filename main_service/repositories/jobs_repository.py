from schemas.jobs_schemas import CreateJobRequest
from fastapi import HTTPException

class JobsRepository:
    def __init__(self):
        self.storage = []

    def get(self, skip: int = 0, limit: int = 10) -> list:
        return self.storage[skip:skip + limit]
    

    def add(self, job: CreateJobRequest) -> dict:
        job_obj = job.model_dump()
        job_obj["id"] = len(self.storage) + 1

        self.storage.append(job_obj )

        return job_obj


    def find_job(self, job_id: int) -> dict:
        for num, job in enumerate(self.storage):
            if job["id"] == job_id:
                return self.storage[num]
            
        raise HTTPException(status_code=404, detail="Job with this id not found")