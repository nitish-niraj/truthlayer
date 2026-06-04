from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from routers.verify import router as verify_router

app = FastAPI(title="TruthLayer API", description="Automated PDF fact-checking backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(verify_router)


@app.get("/")
async def root():
    return {"message": "TruthLayer backend. See /api/health"}
