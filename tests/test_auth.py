import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.dependencies import get_db
from app.routers import user_routes
from sqlalchemy.ext.asyncio import AsyncSession

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.database import Base  # wherever your Base is defined

app = FastAPI()
app.include_router(user_routes.router)

DATABASE_URL = "sqlite+aiosqlite:///:memory:"  # In-memory DB for testing

# Create async engine and session
engine = create_async_engine(DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture()
async def async_session():
    async with TestSessionLocal() as session:
        yield session

# Override FastAPI dependency to use test DB
@app.on_event("startup")
def override_get_db():
    async def _get_db():
        async with TestSessionLocal() as session:
            yield session
    app.dependency_overrides[get_db] = _get_db


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@pytest.mark.asyncio
async def test_login_with_wrong_password(create_test_user, async_session):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/login/",
            data={"username": "john.doe@example.com", "password": "WrongPassword123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password."

@pytest.fixture
async def create_test_user(async_session: AsyncSession):
    from app.models.user_model import User
    from app.utils.security import hash_password

    user = User(
        email="john.doe@example.com",
        hashed_password=hash_password("Secure*1234"),
        email_verified=True,
        nickname="j_doe"
    )
    async_session.add(user)
    await async_session.commit()
    return user