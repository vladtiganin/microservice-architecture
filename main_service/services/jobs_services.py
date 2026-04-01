from schemas.jobs_schemas import CreateJobRequest, JobListResponse
from repositories.jobs_repository import JobsRepository


class JobService:
    def __init__(self, repo: JobsRepository):
        self.repo = repo

    def get_jobs(self, skip:int = 0, limit: int = 10) -> JobListResponse:
        return {"items" : self.repo.get(skip, limit)}
    

    def create_job(self, job: CreateJobRequest) -> dict:
        new_obj = self.repo.add(job)

        return new_obj
    

    def get_job_by_id(self, job_id: int) -> dict:
        return self.repo.find_job(job_id)
