from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.api.routes import router

app = FastAPI(
    title="AI Tech Consultant — Knowledge Brain",
    description="Search the Brilliant Directories support knowledge base.",
    version="1.0.0",
)

app.include_router(router)
