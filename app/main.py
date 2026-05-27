from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth_routes import router as auth_router
from app.config import get_cors_origins
from app.presence_routes import router as presence_router


app = FastAPI(title="Buddy Auth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_cors_origins()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(presence_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": "buddy-auth-api"}
