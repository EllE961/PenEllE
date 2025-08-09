"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import planning

# Create FastAPI app
app = FastAPI(
    title="PenEllE API",
    description="AI-powered research writing pipeline",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(planning.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to PenEllE API", "version": "0.1.0"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
