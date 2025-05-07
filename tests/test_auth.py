import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base
from app.dependencies import get_db
from app.routers import user_routes, auth_routes
from app.utils.security import hash_password
from app.models.user_model import User

# Test database config
DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# Build FastAPI test app
app = FastAPI()
app.include_router(user_routes.router)
app.include_router(auth_routes.router)  # Include /login/ route

# Dependency override
async def override_get_db():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

# Error handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# Fixtures
@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def create_test_user():
    async with TestSessionLocal() as session:
        user = User(
            email="john.doe@example.com",
            hashed_password=hash_password("Secure*1234"),
            email_verified=True,
            nickname="j_doe",
            role="AUTHENTICATED"
        )
        session.add(user)
        await session.commit()

@pytest.mark.asyncio
async def test_login_with_wrong_password(create_test_user):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/login/",
            data={"username": "john.doe@example.com", "password": "WrongPassword123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password."
