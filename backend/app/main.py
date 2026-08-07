from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1.router import router as api_v1_router
from app.exceptions import ConflictError, ForbiddenError, InvalidTokenError, NotFoundError

app = FastAPI(
    title="DashMet API",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Let the browser read the download filename from file responses (e.g. the
    # PPTX export) when the frontend is on a different origin.
    expose_headers=["Content-Disposition"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "version": "0.1.0", "environment": settings.ENVIRONMENT}


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": str(exc)}},
    )


@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError):
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "FORBIDDEN", "message": str(exc)}},
    )


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "CONFLICT", "message": str(exc)}},
    )


@app.exception_handler(InvalidTokenError)
async def invalid_token_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": " -> ".join(str(loc) for loc in err["loc"] if loc != "body"),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": details,
            }
        },
    )
