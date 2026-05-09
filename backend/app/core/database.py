"""MongoDB connection management using motor (async)."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.core.logger import logger


class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


mongo = MongoDB()


async def connect_to_mongo() -> None:
    settings = get_settings()
    logger.info("Connecting to MongoDB at {}", settings.mongo_uri)
    mongo.client = AsyncIOMotorClient(settings.mongo_uri, uuidRepresentation="standard")
    mongo.db = mongo.client[settings.mongo_db]
    await _ensure_indexes()
    logger.success("MongoDB connection established (db={})", settings.mongo_db)


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        mongo.client.close()
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    if mongo.db is None:
        raise RuntimeError("MongoDB is not initialised. Did the lifespan run?")
    return mongo.db


async def _ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("whatsapp_number")
    await db.projects.create_index("slug", unique=True)
    await db.projects.create_index("repository_url")
    await db.tasks.create_index([("project_id", 1), ("created_at", -1)])
    await db.tasks.create_index("whatsapp_chat_id")
    await db.audit_logs.create_index([("created_at", -1)])
    await db.audit_logs.create_index("actor_id")
    await db.code_chunks.create_index([("project_id", 1), ("path", 1)])
    await db.approvals.create_index([("status", 1), ("created_at", -1)])
