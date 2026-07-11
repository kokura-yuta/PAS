from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import hashlib
import secrets
from urllib.parse import quote
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, or_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    Credentials = None
    Flow = None
    GoogleAuthRequest = None
    build = None
    HttpError = Exception


load_dotenv()

CHAT_HISTORY_LIMIT = 10
CHAT_DISPLAY_LIMIT = 50
MEMORY_EXTRACTION_MIN_LENGTH = 20
THREAD_TITLE_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tokyo")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
DIARY_THREAD_TYPE = "diary"
CUSTOM_THREAD_TYPE = "custom"
TIMELINE_LABELS = {
    "past": "過去",
    "present": "現在",
    "future": "未来"
}
THREAD_TYPE_LABELS = {
    DIARY_THREAD_TYPE: "日記",
    CUSTOM_THREAD_TYPE: "自由チャット"
}
MEMORY_SOURCE_LABELS = {
    "user_statement": "本人発言",
    "ai_inference": "AI推測"
}
MEMORY_STATUS_LABELS = {
    "confirmed": "確定",
    "pending": "確認待ち"
}


def truncate_text(text, max_length=60):
    text = (text or "").strip()

    if len(text) <= max_length:
        return text

    return text[:max_length - 1] + "..."


def format_datetime(value):
    if value is None:
        return ""

    return value.strftime("%Y-%m-%d %H:%M")


def get_thread_type_label(thread_type):
    return THREAD_TYPE_LABELS.get(thread_type, "チャット")


def get_thread_description(thread_type):
    if thread_type == DIARY_THREAD_TYPE:
        return "今日あったことや、誰にも話せない気持ちを自由に話してください。文章をきれいにまとめる必要はありません。"

    return "テーマごとにPASと話せる自由チャットです。相談、整理、アイデア出しに使えます。"

DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-session-secret-change-me")
engine = create_engine(DATABASE_URL)

Base = declarative_base()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    email = Column(String(255), unique=True, index=True)
    password_hash = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    __tablename__="chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    role = Column(String(20))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String(200))
    thread_type = Column(String(50), default="custom")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    content = Column(Text)
    category = Column(String(50))
    importance = Column(Integer, default=3)
    confidence = Column(Float, default=0.7)
    source_type = Column(String(50), default="ai_inference")
    status = Column(String(50), default="confirmed")
    is_active = Column(Boolean, default=True)
    last_confirmed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    name = Column(String(100))
    school_year = Column(String(100))
    current_focus = Column(Text)
    life_direction = Column(Text)

    values = Column(Text)
    weaknesses = Column(Text)
    interests = Column(Text)
    communication_preference = Column(Text)

    best_success_experience = Column(Text)
    success_journey = Column(Text)
    success_feelings = Column(Text)
    success_lessons = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    title = Column(String(200))
    description = Column(Text)
    goal_type = Column(String(50), default="short")
    status = Column(String(50), default="active")
    priority = Column(String(50), default="medium")
    deadline = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    default_persona = Column(String(50), default="friend")
    theme_name = Column(String(50), default="calm")
    response_length = Column(String(50), default="auto")
    created_at = Column(DateTime, default=datetime.utcnow)


class TimelineMemory(Base):
    __tablename__ = "timeline_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    content = Column(Text)
    temporal_type = Column(String(50))
    event_date = Column(DateTime)
    emotion = Column(String(100))
    emotion_intensity = Column(Integer, default=3)
    location = Column(String(200))
    related_people = Column(Text)
    importance = Column(Integer, default=3)
    confidence = Column(Float, default=0.7)
    source_type = Column(String(50), default="user_statement")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalendarAccount(Base):
    __tablename__ = "calendar_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    provider = Column(String(50), default="google")
    token_json = Column(Text)
    is_connected = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    google_event_id = Column(String(255), index=True)
    title = Column(String(255))
    description = Column(Text)
    start_datetime = Column(DateTime)
    end_datetime = Column(DateTime)
    location = Column(String(255))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(bind=engine)

def ensure_columns(table_name, column_definitions):
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    column_names = [column["name"] for column in columns]

    with engine.begin() as connection:
        for column_name, column_type in column_definitions.items():
            if column_name not in column_names:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                )


def ensure_chat_message_thread_id_column():
    ensure_columns("chat_messages", {"thread_id": "INTEGER"})

ensure_chat_message_thread_id_column()

def ensure_memory_metadata_columns():
    memory_columns = {
        "importance": "INTEGER DEFAULT 3",
        "confidence": "DOUBLE PRECISION DEFAULT 0.7",
        "source_type": "VARCHAR(50) DEFAULT 'ai_inference'",
        "status": "VARCHAR(50) DEFAULT 'confirmed'",
        "is_active": "BOOLEAN DEFAULT TRUE",
        "last_confirmed_at": "TIMESTAMP"
    }

    ensure_columns("memories", memory_columns)

ensure_memory_metadata_columns()

def ensure_user_id_columns():
    user_tables = [
        "chat_messages",
        "chat_threads",
        "memories",
        "profiles",
        "goals",
        "settings",
        "timeline_memories",
        "calendar_accounts",
        "calendar_events"
    ]

    for table_name in user_tables:
        ensure_columns(table_name, {"user_id": "INTEGER"})


ensure_user_id_columns()

def normalize_email(email):
    return (email or "").strip().lower()


def hash_password(password):
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password, saved_password_hash):
    try:
        salt, expected_hash = saved_password_hash.split("$", 1)
    except ValueError:
        return False

    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000
    ).hex()

    return secrets.compare_digest(actual_hash, expected_hash)


def create_user(name, email, password):
    clean_name = (name or "").strip()
    clean_email = normalize_email(email)

    if not clean_name or not clean_email or len(password) < PASSWORD_MIN_LENGTH:
        return None

    db = SessionLocal()

    try:
        existing_user = db.query(User).filter(User.email == clean_email).first()

        if existing_user:
            return None

        user = User(
            name=clean_name,
            email=clean_email,
            password_hash=hash_password(password)
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        return None
    finally:
        db.close()


def authenticate_user(email, password):
    clean_email = normalize_email(email)
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.email == clean_email).first()

        if user is None or not verify_password(password, user.password_hash):
            return None

        return user
    finally:
        db.close()


def load_user(user_id):
    if user_id is None:
        return None

    db = SessionLocal()

    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def get_current_user(request):
    user_id = request.session.get("user_id")
    return load_user(user_id)


def login_user(request, user_id):
    request.session["user_id"] = user_id
    claim_unowned_data(user_id)
    get_or_create_diary_thread(user_id)
    load_settings(user_id)


def claim_unowned_data(user_id):
    table_names = [
        "chat_messages",
        "chat_threads",
        "memories",
        "profiles",
        "goals",
        "settings",
        "timeline_memories",
        "calendar_accounts",
        "calendar_events"
    ]

    with engine.begin() as connection:
        for table_name in table_names:
            connection.execute(
                text(f"UPDATE {table_name} SET user_id = :user_id WHERE user_id IS NULL"),
                {"user_id": user_id}
            )


def get_or_create_diary_thread(user_id):
    db = SessionLocal()

    try:
        diary_thread = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == DIARY_THREAD_TYPE)
            .first()
        )

        if diary_thread is None:
            diary_thread = ChatThread(
                user_id=user_id,
                title="日記",
                thread_type=DIARY_THREAD_TYPE
            )
            db.add(diary_thread)
            db.commit()
            db.refresh(diary_thread)

        updated_count = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_id == user_id)
            .filter(ChatMessage.thread_id.is_(None))
            .update({"thread_id": diary_thread.id})
        )

        if updated_count:
            db.commit()

        return diary_thread
    finally:
        db.close()


def load_chat_thread(thread_id, user_id):
    db = SessionLocal()

    try:
        thread = (
            db.query(ChatThread)
            .filter(ChatThread.id == thread_id)
            .filter(ChatThread.user_id == user_id)
            .first()
        )

        return thread
    finally:
        db.close()


def load_chat_threads(user_id):
    db = SessionLocal()

    try:
        threads = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .all()
        )

        def sort_thread(thread):
            thread_order = 0 if thread.thread_type == DIARY_THREAD_TYPE else 1
            updated_at = thread.updated_at or thread.created_at or datetime.utcnow()
            return (thread_order, -updated_at.timestamp())

        thread_items = []

        for thread in sorted(threads, key=sort_thread):
            latest_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id)
                .filter(ChatMessage.thread_id == thread.id)
                .order_by(ChatMessage.created_at.desc())
                .first()
            )

            description = get_thread_description(thread.thread_type)
            latest_text = latest_message.content if latest_message else description

            thread_items.append({
                "id": thread.id,
                "title": thread.title,
                "display_title": truncate_text(thread.title, THREAD_TITLE_MAX_LENGTH),
                "thread_type": thread.thread_type,
                "thread_type_label": get_thread_type_label(thread.thread_type),
                "description": description,
                "latest_message": truncate_text(latest_text, 54),
                "updated_at_text": format_datetime(thread.updated_at or thread.created_at),
                "can_delete": thread.thread_type == CUSTOM_THREAD_TYPE
            })

        return thread_items
    finally:
        db.close()


def create_chat_thread(title, user_id):
    clean_title = truncate_text(title, THREAD_TITLE_MAX_LENGTH)

    if not clean_title:
        return None

    db = SessionLocal()

    try:
        thread = ChatThread(
            user_id=user_id,
            title=clean_title,
            thread_type=CUSTOM_THREAD_TYPE
        )

        db.add(thread)
        db.commit()
        db.refresh(thread)

        return thread
    finally:
        db.close()


def delete_chat_thread(thread_id, user_id):
    db = SessionLocal()

    try:
        thread = (
            db.query(ChatThread)
            .filter(ChatThread.id == thread_id)
            .filter(ChatThread.user_id == user_id)
            .first()
        )

        if thread is None or thread.thread_type != CUSTOM_THREAD_TYPE:
            return

        db.query(ChatMessage).filter(ChatMessage.user_id == user_id).filter(ChatMessage.thread_id == thread_id).delete()
        db.delete(thread)
        db.commit()
    finally:
        db.close()


def save_message(role, content, thread_id=None, user_id=None):
    db = SessionLocal()
    try:
        new_message = ChatMessage(
            user_id=user_id,
            thread_id=thread_id,
            role=role,
            content=content
        )

        db.add(new_message)

        if thread_id is not None:
            thread = (
                db.query(ChatThread)
                .filter(ChatThread.id == thread_id)
                .filter(ChatThread.user_id == user_id)
                .first()
            )

            if thread:
                thread.updated_at = datetime.utcnow()

        db.commit()
    finally:
        db.close()


def normalize_importance(value):
    try:
        importance = int(value)
    except (TypeError, ValueError):
        importance = 3

    return max(1, min(5, importance))


def normalize_confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.7

    confidence = max(0.0, min(1.0, confidence))
    return round(confidence, 2)


def normalize_source_type(value):
    if value == "user_statement":
        return "user_statement"

    return "ai_inference"


def format_source_label(source_type):
    source_type = normalize_source_type(source_type)
    return MEMORY_SOURCE_LABELS[source_type]


def normalize_memory_status(value):
    if value == "pending":
        return "pending"

    return "confirmed"


def format_memory_status_label(status):
    status = normalize_memory_status(status)
    return MEMORY_STATUS_LABELS[status]


def decide_memory_status(source_type, confidence):
    source_type = normalize_source_type(source_type)
    confidence = normalize_confidence(confidence)

    if source_type == "user_statement" and confidence >= 0.8:
        return "confirmed"

    return "pending"


def format_date(value):
    if value is None:
        return ""

    return value.strftime("%Y-%m-%d")


def save_memory(
    content,
    category,
    importance=3,
    confidence=0.7,
    source_type="ai_inference",
    status=None,
    user_id=None
):
    content = (content or "").strip()
    category = (category or "").strip()
    importance = normalize_importance(importance)
    confidence = normalize_confidence(confidence)
    source_type = normalize_source_type(source_type)
    status = normalize_memory_status(status or decide_memory_status(source_type, confidence))

    if not content or not category:
        return None

    db = SessionLocal()

    try:
        new_memory = Memory(
            user_id=user_id,
            content=content,
            category=category,
            importance=importance,
            confidence=confidence,
            source_type=source_type,
            status=status,
            is_active=True,
            last_confirmed_at=datetime.utcnow() if status == "confirmed" else None
        )

        db.add(new_memory)
        db.commit()
        db.refresh(new_memory)
        return new_memory.id
    finally:
        db.close()


def save_or_update_memory(
    content,
    category,
    importance=3,
    confidence=0.7,
    source_type="ai_inference",
    status=None,
    user_id=None
):
    content = (content or "").strip()
    category = (category or "").strip()
    importance = normalize_importance(importance)
    confidence = normalize_confidence(confidence)
    source_type = normalize_source_type(source_type)
    status = normalize_memory_status(status or decide_memory_status(source_type, confidence))

    if not content or not category:
        return None

    db = SessionLocal()

    try:
        existing_memory = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .filter(Memory.category == category)
            .filter(Memory.content == content)
            .first()
        )

        if existing_memory:
            current_status = normalize_memory_status(existing_memory.status)
            existing_memory.importance = max(
                normalize_importance(existing_memory.importance),
                importance
            )
            existing_memory.confidence = max(
                normalize_confidence(existing_memory.confidence),
                confidence
            )

            if existing_memory.source_type != "user_statement":
                existing_memory.source_type = source_type

            if current_status == "confirmed" or status == "confirmed":
                existing_memory.status = "confirmed"
                existing_memory.last_confirmed_at = datetime.utcnow()
            else:
                existing_memory.status = "pending"

            db.commit()
            return existing_memory.id

        new_memory = Memory(
            user_id=user_id,
            content=content,
            category=category,
            importance=importance,
            confidence=confidence,
            source_type=source_type,
            status=status,
            is_active=True,
            last_confirmed_at=datetime.utcnow() if status == "confirmed" else None
        )

        db.add(new_memory)
        db.commit()
        db.refresh(new_memory)
        return new_memory.id
    finally:
        db.close()


def load_memories(user_id):
    db = SessionLocal()

    try:
        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .filter(or_(Memory.status == "confirmed", Memory.status.is_(None)))
            .order_by(
                Memory.importance.desc(),
                Memory.confidence.desc(),
                Memory.created_at.desc()
            )
            .limit(20)
            .all()
        )

        memory_text = ""

        for memory in memories:
            importance = normalize_importance(memory.importance)
            confidence = normalize_confidence(memory.confidence)
            source_type = normalize_source_type(memory.source_type)

            memory_text += (
                f"[{memory.category} / importance:{importance} "
                f"/ confidence:{confidence} / source:{source_type}] "
                f"{memory.content}\n"
            )

        return memory_text
    finally:
        db.close()


def load_memory_items(user_id):
    db = SessionLocal()

    try:
        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .order_by(
                Memory.importance.desc(),
                Memory.confidence.desc(),
                Memory.created_at.desc()
            )
            .all()
        )

        memory_items = []

        for memory in memories:
            memory_items.append({
                "id": memory.id,
                "category": memory.category,
                "content": memory.content,
                "importance": normalize_importance(memory.importance),
                "confidence": normalize_confidence(memory.confidence),
                "source_type": normalize_source_type(memory.source_type),
                "source_label": format_source_label(memory.source_type),
                "status": normalize_memory_status(memory.status),
                "status_label": format_memory_status_label(memory.status),
                "is_pending": normalize_memory_status(memory.status) == "pending",
                "is_active": memory.is_active,
                "last_confirmed_at": memory.last_confirmed_at,
                "last_confirmed_text": format_date(memory.last_confirmed_at),
                "created_at": memory.created_at,
                "created_at_text": format_date(memory.created_at)
            })

        return memory_items
    finally:
        db.close()


def confirm_memory(memory_id, user_id):
    db = SessionLocal()

    try:
        memory = (
            db.query(Memory)
            .filter(Memory.id == memory_id)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .first()
        )

        if memory:
            memory.status = "confirmed"
            memory.confidence = max(normalize_confidence(memory.confidence), 0.9)
            memory.last_confirmed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def update_memory(memory_id, user_id, content, category, importance=3, confidence=0.9):
    content = (content or "").strip()
    category = (category or "").strip()
    importance = normalize_importance(importance)
    confidence = max(normalize_confidence(confidence), 0.9)

    if not content or not category:
        return

    db = SessionLocal()

    try:
        memory = (
            db.query(Memory)
            .filter(Memory.id == memory_id)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .first()
        )

        if memory:
            memory.content = content
            memory.category = category
            memory.importance = importance
            memory.confidence = confidence
            memory.source_type = "user_statement"
            memory.status = "confirmed"
            memory.last_confirmed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def delete_memory(memory_id, user_id):
    db = SessionLocal()

    try:
        memory = (
            db.query(Memory)
            .filter(Memory.id == memory_id)
            .filter(Memory.user_id == user_id)
            .first()
        )

        if memory:
            memory.is_active = False
            db.commit()
    finally:
        db.close()

def load_profile(user_id):
    db = SessionLocal()

    try:
        profile = (
            db.query(Profile)
            .filter(Profile.user_id == user_id)
            .order_by(Profile.created_at.desc())
            .first()
        )

        return profile
    finally:
        db.close()

def save_profile(user_id, name, school_year, current_focus, life_direction, values, weaknesses, interests, communication_preference, best_success_experience, success_journey, success_feelings, success_lessons):
    db = SessionLocal()

    try:
        profile = (
            db.query(Profile)
            .filter(Profile.user_id == user_id)
            .order_by(Profile.created_at.desc())
            .first()
        )

        if profile is None:
            profile = Profile(user_id=user_id)
            db.add(profile)

        profile.name = name
        profile.school_year = school_year
        profile.current_focus = current_focus
        profile.life_direction = life_direction
        profile.values = values
        profile.weaknesses = weaknesses
        profile.interests = interests
        profile.communication_preference = communication_preference
        profile.best_success_experience = best_success_experience
        profile.success_journey = success_journey
        profile.success_feelings = success_feelings
        profile.success_lessons = success_lessons

        db.commit()
    finally:
        db.close()


def format_profile_for_prompt(profile):
    if profile is None:
        return "プロフィールはまだ登録されていません。"

    return f"""
名前: {profile.name}
学年・立場: {profile.school_year}
今取り組んでいること: {profile.current_focus}
人生で向かいたい方向性: {profile.life_direction}
大切にしている考え方: {profile.values}
苦手なこと・避けたいこと: {profile.weaknesses}
興味があること: {profile.interests}
PASにどう接してほしいか: {profile.communication_preference}
今までで一番の成功体験: {profile.best_success_experience}
そこまでの道のり: {profile.success_journey}
その時に感じたこと: {profile.success_feelings}
そこから学んだこと: {profile.success_lessons}
"""

def save_goal(user_id, title, description, goal_type, status, priority, deadline):
    db = SessionLocal()

    try:
        new_goal = Goal(
            user_id=user_id,
            title=title,
            description=description,
            goal_type=goal_type,
            status=status,
            priority=priority,
            deadline=deadline
        )

        db.add(new_goal)
        db.commit()
    finally:
        db.close()

def load_goals(user_id):
    db = SessionLocal()

    try:
        goals = (
            db.query(Goal)
            .filter(Goal.user_id == user_id)
            .order_by(Goal.created_at.desc())
            .all()
        )

        return goals
    finally:
        db.close()

def load_settings(user_id):
    db = SessionLocal()

    try:
        settings = (
            db.query(Settings)
            .filter(Settings.user_id == user_id)
            .order_by(Settings.created_at.desc())
            .first()
        )

        if settings is None:
            settings = Settings(user_id=user_id)
            db.add(settings)
            db.commit()

        return settings
    finally:
        db.close()

def save_settings(user_id, default_persona, theme_name, response_length):
    db = SessionLocal()

    try:
        settings = (
            db.query(Settings)
            .filter(Settings.user_id == user_id)
            .order_by(Settings.created_at.desc())
            .first()
        )

        if settings is None:
            settings = Settings(user_id=user_id)
            db.add(settings)

        settings.default_persona = default_persona
        settings.theme_name = theme_name
        settings.response_length = response_length

        db.commit()
    finally:
        db.close()

def format_goals_for_prompt(goals):
    if not goals:
        return "目標はまだ登録されていません。"

    goals_text = ""

    for goal in goals:
        goals_text += f"""
目標名: {goal.title}
種類: {goal.goal_type}
状態: {goal.status}
優先度: {goal.priority}
期限: {goal.deadline}
説明: {goal.description}
"""

    return goals_text

def load_messages(thread_id=None, user_id=None):
    db = SessionLocal()

    try:
        query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

        if thread_id is not None:
            query = query.filter(ChatMessage.thread_id == thread_id)

        messages = query.order_by(ChatMessage.created_at.desc()).limit(CHAT_HISTORY_LIMIT).all()

        history =""

        for msg in reversed(messages):
            history += f"{msg.role}: {msg.content}\n"
        
        return history
    finally:
        db.close()

def load_chat_items(thread_id=None, user_id=None):
    db = SessionLocal()

    try:
        query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

        if thread_id is not None:
            query = query.filter(ChatMessage.thread_id == thread_id)

        messages = query.order_by(ChatMessage.created_at.desc()).limit(CHAT_DISPLAY_LIMIT).all()

        chat_items = []

        for msg in reversed(messages):
            chat_items.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            })

        return chat_items

    finally:
        db.close()


def parse_datetime_value(value):
    value = (value or "").strip()

    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None


def get_timeline_label(temporal_type):
    return TIMELINE_LABELS.get(temporal_type, "未分類")


def save_timeline_memory(
    user_id,
    content,
    temporal_type,
    event_date,
    emotion,
    emotion_intensity,
    location,
    related_people,
    importance,
    confidence,
    source_type="user_statement"
):
    content = (content or "").strip()

    if not content:
        return None

    db = SessionLocal()

    try:
        timeline_memory = TimelineMemory(
            user_id=user_id,
            content=content,
            temporal_type=temporal_type,
            event_date=parse_datetime_value(event_date),
            emotion=(emotion or "").strip(),
            emotion_intensity=normalize_importance(emotion_intensity),
            location=(location or "").strip(),
            related_people=(related_people or "").strip(),
            importance=normalize_importance(importance),
            confidence=normalize_confidence(confidence),
            source_type=normalize_source_type(source_type)
        )

        db.add(timeline_memory)
        db.commit()
        return timeline_memory.id
    finally:
        db.close()


def load_timeline_items(user_id):
    db = SessionLocal()

    try:
        items = (
            db.query(TimelineMemory)
            .filter(TimelineMemory.user_id == user_id)
            .order_by(TimelineMemory.event_date.desc().nullslast(), TimelineMemory.created_at.desc())
            .all()
        )

        timeline_items = []

        for item in items:
            timeline_items.append({
                "id": item.id,
                "content": item.content,
                "temporal_type": item.temporal_type,
                "temporal_label": get_timeline_label(item.temporal_type),
                "event_date_text": format_date(item.event_date),
                "emotion": item.emotion,
                "emotion_intensity": item.emotion_intensity,
                "location": item.location,
                "related_people": item.related_people,
                "importance": normalize_importance(item.importance),
                "confidence": normalize_confidence(item.confidence),
                "source_label": format_source_label(item.source_type)
            })

        return timeline_items
    finally:
        db.close()


def format_timeline_for_prompt(timeline_items):
    if not timeline_items:
        return "Timeline Memoryはまだ登録されていません。"

    timeline_text = ""

    for item in timeline_items[:20]:
        timeline_text += (
            f"[{item['temporal_label']} / date:{item['event_date_text']} "
            f"/ emotion:{item['emotion']} / importance:{item['importance']}] "
            f"{item['content']}\n"
        )

    return timeline_text


def calendar_config_ready():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and Flow and Credentials and build)


def get_calendar_redirect_uri(request):
    if GOOGLE_REDIRECT_URI:
        return GOOGLE_REDIRECT_URI

    return str(request.url_for("google_calendar_callback"))


def build_google_calendar_flow(request):
    if not calendar_config_ready():
        return None

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [get_calendar_redirect_uri(request)]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=CALENDAR_SCOPES,
        redirect_uri=get_calendar_redirect_uri(request)
    )

    return flow


def load_calendar_account(user_id):
    db = SessionLocal()

    try:
        return (
            db.query(CalendarAccount)
            .filter(CalendarAccount.user_id == user_id)
            .filter(CalendarAccount.provider == "google")
            .filter(CalendarAccount.is_connected.is_(True))
            .first()
        )
    finally:
        db.close()


def save_calendar_credentials(user_id, credentials):
    db = SessionLocal()

    try:
        account = (
            db.query(CalendarAccount)
            .filter(CalendarAccount.user_id == user_id)
            .filter(CalendarAccount.provider == "google")
            .first()
        )

        if account is None:
            account = CalendarAccount(user_id=user_id, provider="google")
            db.add(account)

        account.token_json = credentials.to_json()
        account.is_connected = True
        account.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def build_calendar_service(user_id):
    account = load_calendar_account(user_id)

    if not calendar_config_ready():
        return None, "Google Calendar連携の環境変数またはライブラリが未設定です。"

    if account is None or not account.token_json:
        return None, "Google Calendarがまだ接続されていません。"

    credentials = Credentials.from_authorized_user_info(
        json.loads(account.token_json),
        CALENDAR_SCOPES
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        save_calendar_credentials(user_id, credentials)

    if not credentials.valid:
        return None, "Google Calendarの認証が切れています。もう一度接続してください。"

    return build("calendar", "v3", credentials=credentials), ""


def upsert_calendar_event(user_id, event):
    google_event_id = event.get("id")

    if not google_event_id:
        return

    start_value = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
    end_value = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")

    db = SessionLocal()

    try:
        calendar_event = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .filter(CalendarEvent.google_event_id == google_event_id)
            .first()
        )

        if calendar_event is None:
            calendar_event = CalendarEvent(
                user_id=user_id,
                google_event_id=google_event_id
            )
            db.add(calendar_event)

        calendar_event.title = event.get("summary", "無題の予定")
        calendar_event.description = event.get("description", "")
        calendar_event.start_datetime = parse_datetime_value(start_value)
        calendar_event.end_datetime = parse_datetime_value(end_value)
        calendar_event.location = event.get("location", "")
        calendar_event.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def sync_google_calendar_events(user_id):
    service, error = build_calendar_service(user_id)

    if error:
        return False, error

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=90)).isoformat() + "Z"

    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=100,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
    except HttpError:
        return False, "Google Calendarの予定取得に失敗しました。"

    events = events_result.get("items", [])

    for event in events:
        upsert_calendar_event(user_id, event)

    return True, f"{len(events)}件の予定を同期しました。"


def create_google_calendar_event(user_id, title, description, start_datetime, end_datetime, location):
    title = (title or "").strip()
    start_datetime = (start_datetime or "").strip()
    end_datetime = (end_datetime or "").strip()

    if not title or not start_datetime or not end_datetime:
        return False, "予定名、開始日時、終了日時を入力してください。"

    service, error = build_calendar_service(user_id)

    if error:
        return False, error

    event_body = {
        "summary": title,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_datetime,
            "timeZone": APP_TIMEZONE
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": APP_TIMEZONE
        }
    }

    try:
        created_event = service.events().insert(
            calendarId="primary",
            body=event_body
        ).execute()
    except HttpError:
        return False, "Google Calendarへの予定作成に失敗しました。"

    upsert_calendar_event(user_id, created_event)
    return True, "予定を作成しました。"


def delete_google_calendar_event(user_id, calendar_event_id):
    db = SessionLocal()

    try:
        calendar_event = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .filter(CalendarEvent.id == calendar_event_id)
            .first()
        )

        if calendar_event is None:
            return False, "予定が見つかりません。"

        google_event_id = calendar_event.google_event_id
        service, error = build_calendar_service(user_id)

        if not error and google_event_id:
            try:
                service.events().delete(
                    calendarId="primary",
                    eventId=google_event_id
                ).execute()
            except HttpError:
                return False, "Google Calendarの予定削除に失敗しました。"

        db.delete(calendar_event)
        db.commit()
        return True, "予定を削除しました。"
    finally:
        db.close()


def load_calendar_events(user_id):
    db = SessionLocal()

    try:
        events = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .order_by(CalendarEvent.start_datetime.asc().nullslast())
            .all()
        )

        calendar_items = []

        for event in events:
            calendar_items.append({
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "start_text": format_datetime(event.start_datetime),
                "end_text": format_datetime(event.end_datetime),
                "location": event.location
            })

        return calendar_items
    finally:
        db.close()


def format_calendar_for_prompt(calendar_items):
    if not calendar_items:
        return "Google Calendarの予定はまだ取得されていません。"

    calendar_text = ""

    for event in calendar_items[:20]:
        calendar_text += (
            f"{event['start_text']} - {event['end_text']}: "
            f"{event['title']} 場所:{event['location']}\n"
        )

    return calendar_text


def load_home_snapshot(user_id):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    db = SessionLocal()

    try:
        today_events = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .filter(CalendarEvent.start_datetime >= today_start)
            .filter(CalendarEvent.start_datetime < today_end)
            .order_by(CalendarEvent.start_datetime.asc())
            .limit(3)
            .all()
        )

        active_goals = (
            db.query(Goal)
            .filter(Goal.user_id == user_id)
            .filter(Goal.status == "active")
            .order_by(Goal.created_at.desc())
            .limit(3)
            .all()
        )

        key_memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .filter(or_(Memory.status == "confirmed", Memory.status.is_(None)))
            .order_by(Memory.importance.desc(), Memory.confidence.desc())
            .limit(3)
            .all()
        )

        pending_memory_count = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .filter(Memory.status == "pending")
            .count()
        )

        timeline_items = (
            db.query(TimelineMemory)
            .filter(TimelineMemory.user_id == user_id)
            .filter(TimelineMemory.temporal_type.in_(["present", "future"]))
            .order_by(TimelineMemory.importance.desc(), TimelineMemory.event_date.asc().nullslast())
            .limit(3)
            .all()
        )

        today_event_items = [
            {
                "title": event.title,
                "time": format_datetime(event.start_datetime),
                "location": event.location
            }
            for event in today_events
        ]
        goal_items = [
            {
                "title": goal.title,
                "priority": goal.priority,
                "deadline": goal.deadline
            }
            for goal in active_goals
        ]
        memory_items = [memory.content for memory in key_memories]
        timeline_texts = [
            f"{get_timeline_label(item.temporal_type)}: {item.content}"
            for item in timeline_items
        ]

        if today_event_items:
            daily_message = f"今日は「{today_event_items[0]['title']}」があるね。そこに合わせて無理なく整えよう。"
        elif goal_items:
            daily_message = f"今日は「{goal_items[0]['title']}」を少しだけ進める日にしよう。"
        elif timeline_texts:
            daily_message = "今の流れを見ながら、今日の一歩を一緒に決めよう。"
        else:
            daily_message = "今日は何から整える？短くでいいから話してみて。"

        return {
            "daily_message": daily_message,
            "today_events": today_event_items,
            "active_goals": goal_items,
            "key_memories": memory_items,
            "timeline_items": timeline_texts,
            "pending_memory_count": pending_memory_count
        }
    finally:
        db.close()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def extract_memory_from_message(message):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
あなたは、ユーザーの発言から長期記憶に保存すべき情報を抽出するAIです。

保存すべき情報:
- ユーザーの目標
- 価値観
- 性格
- 好み
- 重要な出来事
- 長期的に覚えておくと役立つ情報

保存しなくていい情報:
- あいさつ
- 一時的な雑談
- その場限りの気分
- 意味の薄い短文

必ず次のJSON形式だけで返してください。

保存する情報がある場合:
{{
  "should_save": true,
  "category": "goal",
  "content": "ユーザーは...",
  "importance": 4,
  "confidence": 0.9,
  "source_type": "user_statement"
}}

保存する情報がない場合:
{{
  "should_save": false,
  "category": "",
  "content": "",
  "importance": 0,
  "confidence": 0,
  "source_type": ""
}}

category は goal, value, personality, preference, event, concern, habit の中から選んでください。
importance は 1〜5 の整数で、長期的に重要なほど高くしてください。
confidence は 0〜1 の数値で、ユーザーが明言した情報ほど高くしてください。
source_type は user_statement または ai_inference にしてください。
ユーザーがはっきり言った事実は user_statement、文脈からの推測は ai_inference にしてください。
ai_inference の confidence は 0.65 以下にしてください。推測を事実のように扱わないでください。
content は1つの記憶だけを短い1文にしてください。
同じ内容の記憶が増えにくいように、できるだけ「ユーザーは〜」から始めて具体的に書いてください。

ユーザーの発言:
{message}
"""
    )
    try:
        memory_data = json.loads(response.output_text)

    except json.JSONDecodeError:
        memory_data = {
            "should_save": False,
            "category": "",
            "content": "",
            "importance": 0,
            "confidence": 0,
            "source_type": ""
        }
    return memory_data


PAS_PERSONAS = {
    "friend": """
あなたはPASです。
親しい友達のように、自然で少し砕けた口調で返してください。
固い敬語や説明口調を避け、「そっか」「それはきついね」のような自然な相づちを使ってください。
相手の気持ちを先に受け止め、アドバイスは求められた時や必要な時だけ短く出してください。
""",
    "mentor": """
あなたはPASです。
ユーザーの成長を支えるメンターとして返してください。
まず気持ちを受け止め、そのあと状況を一緒に整理してください。
すぐに正解を押しつけず、ユーザーが自分で気づける質問を1つ入れてください。
提案は最後に、次の一歩だけを具体的に出してください。
""",
    "strict_teacher": """
あなたはPASです。
厳しい先生として、甘やかさずに現実的な視点で返してください。
言い訳や曖昧な考えがある場合は、短くはっきり指摘してください。
ただし人格否定はせず、改善すべき行動・考え方・次の一手を具体的に示してください。
長い説教は避け、刺さる一言と次の行動に絞ってください。
""",
    "secretary": """
あなたはPASです。
秘書として、感情表現よりも整理・要約・優先順位づけを重視して返してください。
要点、現在の状況、次にやることを簡潔にまとめてください。
無駄な雑談は控え、実務的で分かりやすい返答にしてください。
""",
    "life_coach": """
あなたはPASです。
ライフコーチとして、ユーザーの目標・価値観・長期的な成長を踏まえて返してください。
すぐに答えを押しつけるのではなく、必要に応じて問いを使い、ユーザー自身が気づけるように支援してください。
感情に寄り添いながら、前に進むための考え方や行動を提案してください。
	"""
}
RESPONSE_LENGTH_PROMPTS = {
    "auto": """
ユーザーの発言に合わせて長さを自動で決めてください。
短い雑談・感情の吐き出しには1〜3文で返してください。
深い相談・整理が必要な話だけ、必要な分だけ詳しく返してください。
""",
    "concise": """
基本は2〜4文で簡潔に返してください。
必要な時だけ少し補足してください。
""",
    "balanced": """
相談内容に合わせて、短すぎず長すぎない自然な長さで返してください。
必要に応じて、要点と次の行動を分かりやすく伝えてください。
""",
    "detailed": """
理由、手順、具体例を含めて、丁寧に詳しく返してください。
ただし、関係のない説明で長くしすぎないでください
"""
}

PAS_RESPONSE_RULES = """
返答の基本方針:
- その場のノリだけで返さず、ユーザーの状況・目標・過去の情報を踏まえて返してください。
- まず会話として自然に返してください。説明文・レポート・箇条書きに寄りすぎないでください。
- ユーザーの発言が軽い時は自然に短く返してください。
- 決めつけは避け、情報が足りない時は質問してください。
- アドバイスより先に、共感か確認質問を優先してください。
- 1回の返信で質問は原則1つだけにしてください。

相談・意思決定への返答:
1. 気持ちを短く受け止める
2. 何が一番大事か確認する質問を1つ出す
3. 十分に状況が見えている時だけ、選択肢や次の一歩を短く出す

感情・雑談への返答:
1. 気持ちを自然に受け止める
2. 分析しすぎず、相づちを返す
3. 必要なら短い質問を1つだけ出す

知識説明への返答:
1. まず結論を伝える
2. 理由を説明する
3. 具体例を出す
4. 注意点があれば補足する

根拠の扱い:
- プロフィール、目標、長期記憶、直近の会話を根拠として使う場合は、どの情報をもとに考えたか分かるようにしてください。
- 外部情報やネット上の根拠が必要な場合は、今この場で確認できない情報を事実として断言しないでください。
- 推測は推測として伝え、事実と混ぜないでください。
- Core Memoryを使う時は「前も話してたよね」を自然に使ってよいですが、毎回は使わないでください。
"""



def build_thread_prompt(thread_title, thread_type):
    if thread_type == DIARY_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットは日記チャットです。
ユーザーの感情や出来事を受け止めることを優先してください。
ユーザーが明確にアドバイスを求めていない場合、すぐに解決策を押しつけず、共感と短い質問を中心にしてください。
"""

    return f"""
現在のチャット: {thread_title}
このチャットは自由チャットです。
チャット名や会話内容に合わせて、相談・整理・提案・アイデア出しをしてください。
"""


def detect_conversation_mode(message):
    message = (message or "").strip()
    lower_message = message.lower()

    emotion_words = [
        "つらい", "辛い", "しんどい", "不安", "怖い", "疲れた", "きつい",
        "むずい", "難しい", "悲しい", "泣き", "焦る", "やばい", "無理"
    ]
    advice_words = [
        "どうすれば", "どうしたら", "何したら", "なにしたら", "教えて",
        "方法", "やり方", "改善", "相談", "悩み", "選ぶ", "決め"
    ]
    planning_words = [
        "予定", "目標", "計画", "今日", "明日", "来週", "やること",
        "タスク", "進捗", "締切", "面接", "インターン"
    ]

    if any(word in message for word in emotion_words):
        return "empathy"

    if any(word in message for word in planning_words):
        return "planning"

    if any(word in message for word in advice_words) or "?" in message or "？" in message:
        return "advice"

    if "とは" in message or "説明" in message or "なぜ" in message:
        return "knowledge"

    if any(word in lower_message for word in ["why", "how", "what"]):
        return "knowledge"

    if len(message) <= 14:
        return "short_chat"

    return "conversation"


def build_response_style_prompt(message, response_length, thread_type):
    mode = detect_conversation_mode(message)

    if response_length == "concise":
        return """
ユーザーは短めの返答を選んでいます。
原則2〜4文。箇条書きは必要な時だけ。
"""

    if response_length == "detailed":
        return """
ユーザーは詳しめの返答を選んでいます。
ただし最初に結論を出し、長くなる時は見出しを少なくして読みやすくしてください。
"""

    mode_prompts = {
        "short_chat": """
今回の発言は短い会話です。
1〜2文で自然に返してください。
分析・長い説明・箇条書きは禁止です。
必要なら短い質問を1つだけ返してください。
""",
        "empathy": """
今回の発言は感情の吐き出しです。
最初は共感を優先してください。
すぐに解決策を並べず、1〜3文で受け止めてから、短い質問を1つだけしてください。
""",
        "planning": """
今回の発言は予定・目標・行動に関係しています。
まず状況を短く受け止め、今日できる一歩を1つだけ提案してください。
CalendarやTimelineに関係する情報があれば自然に使ってください。
""",
        "advice": """
今回の発言は相談です。
共感→確認質問→必要なら小さい提案、の順番で返してください。
最初から選択肢を大量に出さないでください。
""",
        "knowledge": """
今回の発言は説明を求めています。
最初に結論を短く出し、そのあと必要な理由や例を加えてください。
""",
        "conversation": """
今回の発言は通常会話です。
会話の流れを優先し、長く説明しすぎないでください。
"""
    }

    if thread_type == DIARY_THREAD_TYPE and mode in ["empathy", "conversation", "short_chat"]:
        return mode_prompts[mode] + """
日記チャットなので、評価や説教よりも、気持ちを言葉にする支援を優先してください。
"""

    return mode_prompts[mode]


def build_ai_prompt(
    message,
    history,
    memories,
    timeline_text,
    calendar_text,
    profile_text,
    goals_text,
    persona="friend",
    response_length="balanced",
    thread_title="日記",
    thread_type=DIARY_THREAD_TYPE
):
    persona_prompt = PAS_PERSONAS.get(persona, PAS_PERSONAS["friend"])
    length_prompt = RESPONSE_LENGTH_PROMPTS.get(response_length, RESPONSE_LENGTH_PROMPTS["balanced"])
    response_style_prompt = build_response_style_prompt(message, response_length, thread_type)
    thread_prompt = build_thread_prompt(thread_title, thread_type)
    return f"""
{persona_prompt}

PASの返答ルール:
{PAS_RESPONSE_RULES}

チャットの種類:
{thread_prompt}

返答の長さ:
{length_prompt}

今回の返し方:
{response_style_prompt}

プロフィール:
{profile_text}

目標:
{goals_text}

長期記憶:
{memories}

Timeline Memory:
{timeline_text}

Google Calendar予定:
{calendar_text}

これまでの会話:
{history}

ユーザーの今回の発言:
{message}
"""

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")

@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "",
            "name": "",
            "email": ""
        }
    )


@app.post("/signup")
def signup_action(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form("")
):
    user = create_user(name, email, password)

    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "settings": {"theme_name": "calm"},
                "error": f"名前・メール・{PASSWORD_MIN_LENGTH}文字以上のパスワードを確認してください。",
                "name": name,
                "email": email
            }
        )

    login_user(request, user.id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "",
            "email": ""
        }
    )


@app.post("/login")
def login_action(
    request: Request,
    email: str = Form(""),
    password: str = Form("")
):
    user = authenticate_user(email, password)

    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "settings": {"theme_name": "calm"},
                "error": "メールアドレスかパスワードが違います。",
                "email": email
            }
        )

    login_user(request, user.id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
def home(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)
    get_or_create_diary_thread(current_user.id)
    chat_threads = load_chat_threads(current_user.id)
    home_snapshot = load_home_snapshot(current_user.id)
    custom_thread_count = sum(
        1 for thread in chat_threads if thread["thread_type"] == CUSTOM_THREAD_TYPE
    )

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "settings": settings,
            "current_user": current_user,
            "home_snapshot": home_snapshot,
            "chat_threads": chat_threads,
            "custom_thread_count": custom_thread_count,
            "thread_title_max_length": THREAD_TITLE_MAX_LENGTH
        }
    )

@app.get("/chat")
def chat_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)
    diary_thread = get_or_create_diary_thread(current_user.id)
    chat_items = load_chat_items(diary_thread.id, current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "settings": settings,
            "chat_items": chat_items,
            "thread_id": diary_thread.id,
            "thread_title": diary_thread.title,
            "thread_description": get_thread_description(diary_thread.thread_type),
            "thread_type_label": get_thread_type_label(diary_thread.thread_type),
            "can_delete_thread": False
        }
    )

@app.get("/chat/{thread_id}")
def chat_thread_page(request: Request, thread_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)
    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return RedirectResponse(url="/", status_code=303)

    chat_items = load_chat_items(thread_id, current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "settings": settings,
            "chat_items": chat_items,
            "thread_id": thread_id,
            "thread_title": thread.title,
            "thread_description": get_thread_description(thread.thread_type),
            "thread_type_label": get_thread_type_label(thread.thread_type),
            "can_delete_thread": thread.thread_type == CUSTOM_THREAD_TYPE
        }
    )

@app.post("/chat_threads")
def chat_thread_create(request: Request, title: str = Form("")):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    clean_title = title.strip()

    if not clean_title:
        return RedirectResponse(url="/", status_code=303)

    thread = create_chat_thread(clean_title, current_user.id)

    if thread is None:
        return RedirectResponse(url="/", status_code=303)

    return RedirectResponse(url=f"/chat/{thread.id}", status_code=303)

@app.post("/chat_threads/{thread_id}/delete")
def chat_thread_delete(request: Request, thread_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    delete_chat_thread(thread_id, current_user.id)

    return RedirectResponse(url="/", status_code=303)

@app.get("/memories")
def memories_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    memories = load_memory_items(current_user.id)
    pending_memories = [memory for memory in memories if memory["is_pending"]]
    confirmed_memories = [memory for memory in memories if not memory["is_pending"]]
    settings = load_settings(current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="memories.html",
        context={
            "memories": memories,
            "pending_memories": pending_memories,
            "confirmed_memories": confirmed_memories,
            "settings": settings
        }
    )

@app.get("/profile")
def profile_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    profile = load_profile(current_user.id)
    settings = load_settings(current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "profile": profile,
            "settings": settings
        }
    )

@app.post("/profile")
def profile_save(
    request: Request,
    name: str = Form(""),
    school_year: str = Form(""),
    current_focus: str = Form(""),
    life_direction: str = Form(""),
    values: str = Form(""),
    weaknesses: str = Form(""),
    interests: str = Form(""),
    communication_preference: str = Form(""),
    best_success_experience: str = Form(""),
    success_journey: str = Form(""),
    success_feelings: str = Form(""),
    success_lessons: str = Form("")
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    save_profile(
        user_id=current_user.id,
        name=name,
        school_year=school_year,
        current_focus=current_focus,
        life_direction=life_direction,
        values=values,
        weaknesses=weaknesses,
        interests=interests,
        communication_preference=communication_preference,
        best_success_experience=best_success_experience,
        success_journey=success_journey,
        success_feelings=success_feelings,
        success_lessons=success_lessons
    )

    return RedirectResponse(url="/profile", status_code=303)

@app.get("/goals")
def goals_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    goals = load_goals(current_user.id)
    settings = load_settings(current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="goals.html",
        context={
            "goals": goals,
            "settings": settings
        }
    )

@app.post("/goals")
def goal_save(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    goal_type: str = Form("short"),
    status: str = Form("active"),
    priority: str = Form("medium"),
    deadline: str = Form("")
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    save_goal(
        user_id=current_user.id,
        title=title,
        description=description,
        goal_type=goal_type,
        status=status,
        priority=priority,
        deadline=deadline
    )

    return RedirectResponse(url="/goals", status_code=303)


@app.get("/timeline")
def timeline_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)
    timeline_items = load_timeline_items(current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="timeline.html",
        context={
            "settings": settings,
            "timeline_items": timeline_items
        }
    )


@app.post("/timeline")
def timeline_save(
    request: Request,
    content: str = Form(""),
    temporal_type: str = Form("present"),
    event_date: str = Form(""),
    emotion: str = Form(""),
    emotion_intensity: int = Form(3),
    location: str = Form(""),
    related_people: str = Form(""),
    importance: int = Form(3),
    confidence: float = Form(0.8)
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    save_timeline_memory(
        user_id=current_user.id,
        content=content,
        temporal_type=temporal_type,
        event_date=event_date,
        emotion=emotion,
        emotion_intensity=emotion_intensity,
        location=location,
        related_people=related_people,
        importance=importance,
        confidence=confidence
    )

    return RedirectResponse(url="/timeline", status_code=303)


@app.get("/calendar")
def calendar_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)
    calendar_account = load_calendar_account(current_user.id)
    calendar_items = load_calendar_events(current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "settings": settings,
            "calendar_ready": calendar_config_ready(),
            "calendar_connected": calendar_account is not None,
            "calendar_items": calendar_items,
            "message": request.query_params.get("message", "")
        }
    )


@app.get("/calendar/connect")
def google_calendar_connect(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    flow = build_google_calendar_flow(request)

    if flow is None:
        return RedirectResponse(url=f"/calendar?message={quote('Google Calendar設定が未完了です')}", status_code=303)

    state = secrets.token_urlsafe(24)
    request.session["google_calendar_oauth_state"] = state
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state
    )

    return RedirectResponse(url=authorization_url, status_code=303)


@app.get("/calendar/callback")
def google_calendar_callback(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    expected_state = request.session.get("google_calendar_oauth_state")
    received_state = request.query_params.get("state")

    if not expected_state or expected_state != received_state:
        return RedirectResponse(url=f"/calendar?message={quote('Google Calendar接続の確認に失敗しました')}", status_code=303)

    flow = build_google_calendar_flow(request)

    if flow is None:
        return RedirectResponse(url=f"/calendar?message={quote('Google Calendar設定が未完了です')}", status_code=303)

    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception:
        return RedirectResponse(url=f"/calendar?message={quote('Google Calendar接続に失敗しました')}", status_code=303)

    save_calendar_credentials(current_user.id, flow.credentials)
    sync_google_calendar_events(current_user.id)

    return RedirectResponse(url=f"/calendar?message={quote('Google Calendarを接続しました')}", status_code=303)


@app.post("/calendar/sync")
def calendar_sync(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    _, message = sync_google_calendar_events(current_user.id)
    return RedirectResponse(url=f"/calendar?message={quote(message)}", status_code=303)


@app.post("/calendar/events")
def calendar_event_create(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    start_datetime: str = Form(""),
    end_datetime: str = Form(""),
    location: str = Form("")
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    _, message = create_google_calendar_event(
        user_id=current_user.id,
        title=title,
        description=description,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        location=location
    )

    return RedirectResponse(url=f"/calendar?message={quote(message)}", status_code=303)


@app.post("/calendar/events/{calendar_event_id}/delete")
def calendar_event_delete(request: Request, calendar_event_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    _, message = delete_google_calendar_event(current_user.id, calendar_event_id)
    return RedirectResponse(url=f"/calendar?message={quote(message)}", status_code=303)


@app.get("/settings")
def settings_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    settings = load_settings(current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": settings
        }
    )

@app.post("/settings")
def settings_save(
    request: Request,
    default_persona: str = Form("friend"),
    theme_name: str = Form("calm"),
    response_length: str = Form("balanced")
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    save_settings(
        user_id=current_user.id,
        default_persona=default_persona,
        theme_name=theme_name,
        response_length=response_length
    )

    return RedirectResponse(url="/settings", status_code=303)

@app.post("/chat/{thread_id}")
def chat_send(request: Request, thread_id: int, message: str = Form(...)):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return RedirectResponse(url="/", status_code=303)

    clean_message = message.strip()

    if not clean_message:
        return RedirectResponse(url=f"/chat/{thread_id}", status_code=303)

    history = load_messages(thread_id, current_user.id)
    memories = load_memories(current_user.id)
    timeline_items = load_timeline_items(current_user.id)
    timeline_text = format_timeline_for_prompt(timeline_items)
    calendar_items = load_calendar_events(current_user.id)
    calendar_text = format_calendar_for_prompt(calendar_items)
    profile = load_profile(current_user.id)
    profile_text = format_profile_for_prompt(profile)
    goals = load_goals(current_user.id)
    goals_text = format_goals_for_prompt(goals)
    settings = load_settings(current_user.id)
    persona = settings.default_persona
    response_length = settings.response_length

    save_message("user", clean_message, thread_id, current_user.id)

    memory_data = {
        "should_save": False,
        "category": "",
        "content": "",
        "importance": 0,
        "confidence": 0,
        "source_type": ""
    }

    if len(clean_message) >= MEMORY_EXTRACTION_MIN_LENGTH:
        try:
            memory_data = extract_memory_from_message(clean_message)
        except Exception:
            memory_data = {
                "should_save": False,
                "category": "",
                "content": "",
                "importance": 0,
                "confidence": 0,
                "source_type": ""
            }

    should_save_memory = (
        memory_data.get("should_save")
        and memory_data.get("content")
        and memory_data.get("category")
    )

    if should_save_memory:
        save_or_update_memory(
            content=memory_data["content"],
            category=memory_data["category"],
            importance=memory_data.get("importance", 3),
            confidence=memory_data.get("confidence", 0.7),
            source_type=memory_data.get("source_type", "ai_inference"),
            user_id=current_user.id
        )


    ai_message = ""
    should_save_ai_message = True

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=build_ai_prompt(
                clean_message,
                history,
                memories,
                timeline_text,
                calendar_text,
                profile_text,
                goals_text,
                persona,
                response_length,
                thread.title,
                thread.thread_type
            )
        )

        ai_message = response.output_text
    except Exception:
        ai_message = "PASの回答を生成できませんでした。もう一度送信してください。"
        should_save_ai_message = False

    if should_save_ai_message:
        save_message("assistant", ai_message, thread_id, current_user.id)

    chat_items = load_chat_items(thread_id, current_user.id)

    if not should_save_ai_message:
        chat_items.append({
            "role": "assistant",
            "content": ai_message,
            "created_at": datetime.utcnow()
        })

    
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "chat_items": chat_items,
            "settings": settings,
            "thread_id": thread_id,
            "thread_title": thread.title,
            "thread_description": get_thread_description(thread.thread_type),
            "thread_type_label": get_thread_type_label(thread.thread_type),
            "can_delete_thread": thread.thread_type == CUSTOM_THREAD_TYPE
            }
    )

@app.post("/memories/{memory_id}/delete")
def delete_memory_action(request: Request, memory_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    delete_memory(memory_id, current_user.id)
    return RedirectResponse(url="/memories", status_code=303)


@app.post("/memories/{memory_id}/confirm")
def confirm_memory_action(request: Request, memory_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    confirm_memory(memory_id, current_user.id)
    return RedirectResponse(url="/memories", status_code=303)


@app.post("/memories/{memory_id}/update")
def update_memory_action(
    request: Request,
    memory_id: int,
    content: str = Form(""),
    category: str = Form(""),
    importance: int = Form(3),
    confidence: float = Form(0.9)
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    update_memory(
        memory_id=memory_id,
        user_id=current_user.id,
        content=content,
        category=category,
        importance=importance,
        confidence=confidence
    )
    return RedirectResponse(url="/memories", status_code=303)
