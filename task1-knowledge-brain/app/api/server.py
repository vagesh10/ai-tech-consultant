
from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="AI Tech Consultant — Knowledge Brain",
    description="Search the Brilliant Directories support knowledge base.",
    version="1.0.0",
)

app.include_router(router)
