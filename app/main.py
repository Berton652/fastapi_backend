from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import Base, get_engine
from .routers import auth, conversions, wallets


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenient for development. For production, manage the schema with Alembic migrations.
    Base.metadata.create_all(get_engine())
    yield


app = FastAPI(title="OnePoint API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    """Flatten FastAPI's 422 list into the single string the mobile app expects in `detail`."""
    messages = []
    for err in exc.errors():
        msg = str(err.get("msg", "Invalid value"))
        if err.get("type") == "value_error":
            messages.append(msg.removeprefix("Value error, "))
        else:
            field = next((str(p) for p in reversed(err.get("loc", ())) if p != "body"), "request")
            messages.append(f"{field}: {msg}")
    return JSONResponse(status_code=422, content={"detail": " ".join(messages) or "Invalid request."})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(wallets.router)
app.include_router(conversions.router)
