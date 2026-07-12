from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
import os
import json
import hashlib
import secrets
import base64
import re
from urllib.parse import quote
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, or_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


load_dotenv()

CHAT_HISTORY_LIMIT = 10
CHAT_DISPLAY_LIMIT = 50
MEMORY_EXTRACTION_MIN_LENGTH = 20
THREAD_TITLE_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tokyo")
DIARY_THREAD_TYPE = "diary"
CUSTOM_THREAD_TYPE = "custom"
WORK_THREAD_TYPE = "work"
STUDY_THREAD_TYPE = "study"
ASSET_VERSION = (os.getenv("RENDER_GIT_COMMIT") or "study-20260712-1")[:12]
FITNESS_THREAD_TYPE = "fitness"
MENTAL_THREAD_TYPE = "mental"
FINANCE_THREAD_TYPE = "finance"
HEALTH_THREAD_TYPE = "health"
SPECIALIST_THREAD_TYPES = {
    WORK_THREAD_TYPE,
    STUDY_THREAD_TYPE,
    FITNESS_THREAD_TYPE,
    MENTAL_THREAD_TYPE,
    FINANCE_THREAD_TYPE,
    HEALTH_THREAD_TYPE
}
CREATABLE_THREAD_TYPES = SPECIALIST_THREAD_TYPES | {CUSTOM_THREAD_TYPE}
TIMELINE_LABELS = {
    "past": "過去",
    "present": "現在",
    "future": "未来"
}
THREAD_TYPE_LABELS = {
    DIARY_THREAD_TYPE: "日記",
    CUSTOM_THREAD_TYPE: "自由チャット",
    WORK_THREAD_TYPE: "Work PAS",
    STUDY_THREAD_TYPE: "Study PAS",
    FITNESS_THREAD_TYPE: "Fitness PAS",
    MENTAL_THREAD_TYPE: "Mental PAS",
    FINANCE_THREAD_TYPE: "Finance PAS",
    HEALTH_THREAD_TYPE: "Health PAS"
}
MEMORY_SOURCE_LABELS = {
    "user_statement": "本人発言",
    "ai_inference": "AI推測"
}
MEMORY_STATUS_LABELS = {
    "confirmed": "確定",
    "pending": "確認待ち"
}
SUBJECT_EXAMPLES = ["英語", "数学", "Python", "Java", "TOEIC", "基本情報", "大学数学"]
STUDY_IMAGE_MAX_BYTES = 7 * 1024 * 1024


class ChatThreadCreatePayload(BaseModel):
    title: str = ""
    thread_type: str = CUSTOM_THREAD_TYPE


class ChatMessageCreatePayload(BaseModel):
    message: str = ""


def get_app_timezone():
    try:
        return ZoneInfo(APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=9))


def app_now():
    return datetime.now(get_app_timezone()).replace(tzinfo=None)


def get_today_range():
    now = datetime.now(get_app_timezone())
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    return today_start.replace(tzinfo=None), today_end.replace(tzinfo=None)


def format_current_datetime_for_prompt():
    now = datetime.now(get_app_timezone())
    weekday_labels = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_labels[now.weekday()]

    return f"{now.strftime('%Y-%m-%d')}（{weekday}）{now.strftime('%H:%M')} / timezone:{APP_TIMEZONE}"


def truncate_text(text, max_length=60):
    text = (text or "").strip()

    if len(text) <= max_length:
        return text

    return text[:max_length - 1] + "..."


def format_datetime(value):
    if value is None:
        return ""

    return value.strftime("%Y-%m-%d %H:%M")


def format_datetime_local_value(value):
    if value is None:
        return ""

    return value.strftime("%Y-%m-%dT%H:%M")


def get_thread_type_label(thread_type):
    return THREAD_TYPE_LABELS.get(thread_type, "チャット")


def get_thread_description(thread_type):
    if thread_type == DIARY_THREAD_TYPE:
        return "今日あったことや、誰にも話せない気持ちを自由に話してください。文章をきれいにまとめる必要はありません。"

    if thread_type == WORK_THREAD_TYPE:
        return "就活、面接、ES、キャリア設計を、あなたの目標や予定とつなげて整理します。"

    if thread_type == STUDY_THREAD_TYPE:
        return "勉強、資格、大学、学習計画を、今の理解度と目標に合わせて支援します。"

    if thread_type == FITNESS_THREAD_TYPE:
        return "筋トレ、食事、睡眠、継続を、生活状況に合わせて無理なく整えます。"

    if thread_type == MENTAL_THREAD_TYPE:
        return "感情整理、ストレス、不安、自己理解を、急がず一緒に言葉にします。"

    if thread_type == FINANCE_THREAD_TYPE:
        return "お金、貯金、支出、将来設計を、現実的な行動に落とし込みます。"

    if thread_type == HEALTH_THREAD_TYPE:
        return "体調、睡眠、生活習慣、通院予定を、無理なく続けられる形に整えます。"

    return "テーマごとにPASと話せる自由チャットです。相談、整理、アイデア出しに使えます。"


def get_specialist_thread_title(thread_type):
    titles = {
        WORK_THREAD_TYPE: "Work PAS",
        STUDY_THREAD_TYPE: "Study PAS",
        FITNESS_THREAD_TYPE: "Fitness PAS",
        MENTAL_THREAD_TYPE: "Mental PAS",
        FINANCE_THREAD_TYPE: "Finance PAS",
        HEALTH_THREAD_TYPE: "Health PAS"
    }

    return titles.get(thread_type, "新しいチャット")

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
    created_at = Column(DateTime, default=app_now)

class ChatMessage(Base):
    __tablename__="chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    role = Column(String(20))
    content = Column(Text)
    created_at = Column(DateTime, default=app_now)

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String(200))
    thread_type = Column(String(50), default="custom")
    last_studied_at = Column(DateTime)
    study_session_count = Column(Integer, default=0)
    study_streak_count = Column(Integer, default=0)
    last_study_date = Column(String(20))
    test_date = Column(String(50))
    deadline = Column(String(50))
    created_at = Column(DateTime, default=app_now)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


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
    created_at = Column(DateTime, default=app_now)

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

    created_at = Column(DateTime, default=app_now)

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

    created_at = Column(DateTime, default=app_now)

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    default_persona = Column(String(50), default="friend")
    theme_name = Column(String(50), default="calm")
    response_length = Column(String(50), default="auto")
    created_at = Column(DateTime, default=app_now)


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
    created_at = Column(DateTime, default=app_now)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String(255))
    description = Column(Text)
    start_datetime = Column(DateTime)
    end_datetime = Column(DateTime)
    location = Column(String(255))
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


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

def ensure_chat_thread_study_columns():
    ensure_columns(
        "chat_threads",
        {
            "last_studied_at": "TIMESTAMP",
            "study_session_count": "INTEGER DEFAULT 0",
            "study_streak_count": "INTEGER DEFAULT 0",
            "last_study_date": "VARCHAR(20)",
            "test_date": "VARCHAR(50)",
            "deadline": "VARCHAR(50)"
        }
    )

ensure_chat_thread_study_columns()

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


def normalize_subject_title(title):
    clean_title = " ".join((title or "").strip().split())

    if not clean_title:
        return ""

    return truncate_text(clean_title, THREAD_TITLE_MAX_LENGTH)


def get_or_create_default_study_thread(user_id):
    db = SessionLocal()

    try:
        study_thread = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .order_by(ChatThread.updated_at.desc().nullslast(), ChatThread.created_at.desc())
            .first()
        )

        if study_thread is None:
            study_thread = ChatThread(
                user_id=user_id,
                title="学習相談",
                thread_type=STUDY_THREAD_TYPE
            )
            db.add(study_thread)
            db.commit()
            db.refresh(study_thread)

        return study_thread
    finally:
        db.close()


def get_study_days_since(last_studied_at):
    if last_studied_at is None:
        return None

    today = datetime.now(get_app_timezone()).date()
    return (today - last_studied_at.date()).days


def serialize_study_context(thread):
    days_since_last = get_study_days_since(thread.last_studied_at)
    session_count = thread.study_session_count or 0
    streak_count = thread.study_streak_count or 0

    if days_since_last is None:
        last_studied_label = "まだ学習していません"
        status_line = "この科目はこれから一緒に育てる学習チャットです。"
    elif days_since_last == 0:
        last_studied_label = "今日学習しました"
        status_line = f"今日は{thread.title}を進めています。"
    elif days_since_last == 1:
        last_studied_label = "昨日学習しました"
        status_line = f"昨日の{thread.title}の続きから始められます。"
    else:
        last_studied_label = f"{days_since_last}日前に学習しました"
        status_line = f"{days_since_last}日ぶりの{thread.title}です。まず前回の復習から入れます。"

    return {
        "subject": thread.title,
        "last_studied_label": last_studied_label,
        "days_since_last": days_since_last,
        "session_count": session_count,
        "streak_count": streak_count,
        "test_date": thread.test_date or "",
        "deadline": thread.deadline or "",
        "status_line": status_line
    }


def format_study_context_for_prompt(thread):
    context = serialize_study_context(thread)

    return f"""
科目: {context["subject"]}
学習状況: {context["status_line"]}
最終学習: {context["last_studied_label"]}
学習回数: {context["session_count"]}
連続学習日数: {context["streak_count"]}
テスト日: {context["test_date"] or "未登録"}
提出期限: {context["deadline"] or "未登録"}
"""


def record_study_activity(thread_id, user_id):
    db = SessionLocal()

    try:
        thread = (
            db.query(ChatThread)
            .filter(ChatThread.id == thread_id)
            .filter(ChatThread.user_id == user_id)
            .first()
        )

        if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
            return

        today = datetime.now(get_app_timezone()).date()
        previous_date = None

        if thread.last_study_date:
            try:
                previous_date = datetime.strptime(thread.last_study_date, "%Y-%m-%d").date()
            except ValueError:
                previous_date = None

        thread.last_studied_at = app_now()
        thread.study_session_count = (thread.study_session_count or 0) + 1

        if previous_date == today:
            thread.study_streak_count = max(thread.study_streak_count or 1, 1)
        elif previous_date == today - timedelta(days=1):
            thread.study_streak_count = (thread.study_streak_count or 0) + 1
        else:
            thread.study_streak_count = 1

        thread.last_study_date = today.isoformat()
        thread.updated_at = app_now()
        db.commit()
    finally:
        db.close()


def infer_date_from_message(message):
    message = (message or "").strip()
    today = datetime.now(get_app_timezone()).date()

    if not message:
        return None

    explicit_date = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?", message)

    if explicit_date:
        try:
            return datetime(
                int(explicit_date.group(1)),
                int(explicit_date.group(2)),
                int(explicit_date.group(3))
            ).date()
        except ValueError:
            return None

    month_day = re.search(r"(\d{1,2})月(\d{1,2})日?", message)

    if month_day:
        try:
            candidate = datetime(today.year, int(month_day.group(1)), int(month_day.group(2))).date()
            if candidate < today:
                candidate = datetime(today.year + 1, int(month_day.group(1)), int(month_day.group(2))).date()
            return candidate
        except ValueError:
            return None

    days_after = re.search(r"(\d{1,2})日後", message)

    if days_after:
        return today + timedelta(days=int(days_after.group(1)))

    if "明後日" in message:
        return today + timedelta(days=2)

    if "明日" in message:
        return today + timedelta(days=1)

    if "今日" in message:
        return today

    if "来週" in message:
        weekday_map = {
            "月": 0,
            "火": 1,
            "水": 2,
            "木": 3,
            "金": 4,
            "土": 5,
            "日": 6
        }

        for label, weekday in weekday_map.items():
            if f"来週{label}" in message or f"来週の{label}" in message:
                days_until_next_week = 7 - today.weekday() + weekday
                return today + timedelta(days=days_until_next_week)

        return today + timedelta(days=7)

    if "来月" in message:
        year = today.year
        month = today.month + 1

        if month == 13:
            year += 1
            month = 1

        return datetime(year, month, min(today.day, 28)).date()

    return None


def update_study_schedule_from_message(thread_id, user_id, message):
    inferred_date = infer_date_from_message(message)

    if inferred_date is None:
        return

    db = SessionLocal()

    try:
        thread = (
            db.query(ChatThread)
            .filter(ChatThread.id == thread_id)
            .filter(ChatThread.user_id == user_id)
            .first()
        )

        if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
            return

        test_keywords = ["テスト", "試験", "小テスト", "模試", "検定", "受験"]
        deadline_keywords = ["提出", "締切", "締め切り", "期限", "課題", "レポート"]
        date_text = inferred_date.isoformat()

        if any(keyword in message for keyword in test_keywords):
            thread.test_date = date_text

        if any(keyword in message for keyword in deadline_keywords):
            thread.deadline = date_text

        thread.updated_at = app_now()
        db.commit()
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
            if thread.thread_type == DIARY_THREAD_TYPE:
                thread_order = 0
            elif thread.thread_type in SPECIALIST_THREAD_TYPES:
                thread_order = 1
            else:
                thread_order = 2
            updated_at = thread.updated_at or thread.created_at or app_now()
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
                "can_delete": thread.thread_type != DIARY_THREAD_TYPE
            })

        return thread_items
    finally:
        db.close()


def load_study_threads(user_id):
    db = SessionLocal()

    try:
        threads = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .order_by(ChatThread.updated_at.desc().nullslast(), ChatThread.created_at.desc())
            .all()
        )

        study_threads = []

        for thread in threads:
            latest_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id)
                .filter(ChatMessage.thread_id == thread.id)
                .order_by(ChatMessage.created_at.desc())
                .first()
            )

            study_threads.append({
                "id": thread.id,
                "title": thread.title,
                "display_title": truncate_text(thread.title, THREAD_TITLE_MAX_LENGTH),
                "latest_message": truncate_text(
                    latest_message.content if latest_message else "まだ授業は始まっていません。",
                    64
                ),
                "updated_at_text": format_datetime(thread.updated_at or thread.created_at),
                "study_context": serialize_study_context(thread),
                "can_delete": True
            })

        return study_threads
    finally:
        db.close()


def create_chat_thread(title, user_id, thread_type=CUSTOM_THREAD_TYPE):
    clean_title = normalize_subject_title(title)
    thread_type = thread_type if thread_type in CREATABLE_THREAD_TYPES else CUSTOM_THREAD_TYPE

    if not clean_title:
        return None

    db = SessionLocal()

    try:
        thread = ChatThread(
            user_id=user_id,
            title=clean_title,
            thread_type=thread_type
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

        if thread is None or thread.thread_type == DIARY_THREAD_TYPE:
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
                thread.updated_at = app_now()

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
            last_confirmed_at=app_now() if status == "confirmed" else None
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
                existing_memory.last_confirmed_at = app_now()
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
            last_confirmed_at=app_now() if status == "confirmed" else None
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
            memory.last_confirmed_at = app_now()
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
            memory.last_confirmed_at = app_now()
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


def save_local_calendar_event(user_id, title, description, start_datetime, end_datetime, location):
    title = (title or "").strip()
    description = (description or "").strip()
    location = (location or "").strip()
    start_value = parse_datetime_value(start_datetime)
    end_value = parse_datetime_value(end_datetime)

    if not title or start_value is None or end_value is None:
        return False, "予定名、開始日時、終了日時を入力してください。"

    if end_value < start_value:
        return False, "終了日時は開始日時より後にしてください。"

    db = SessionLocal()

    try:
        calendar_event = CalendarEvent(
            user_id=user_id,
            title=title,
            description=description,
            start_datetime=start_value,
            end_datetime=end_value,
            location=location
        )

        db.add(calendar_event)
        db.commit()
        return True, "PAS内の予定として保存しました。"
    finally:
        db.close()


def create_calendar_event(user_id, title, description, start_datetime, end_datetime, location):
    return save_local_calendar_event(
        user_id=user_id,
        title=title,
        description=description,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        location=location
    )


def update_calendar_event(user_id, calendar_event_id, title, description, start_datetime, end_datetime, location):
    title = (title or "").strip()
    description = (description or "").strip()
    location = (location or "").strip()
    start_value = parse_datetime_value(start_datetime)
    end_value = parse_datetime_value(end_datetime)

    if not title or start_value is None or end_value is None:
        return False, "予定名、開始日時、終了日時を入力してください。"

    if end_value < start_value:
        return False, "終了日時は開始日時より後にしてください。"

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

        calendar_event.title = title
        calendar_event.description = description
        calendar_event.start_datetime = start_value
        calendar_event.end_datetime = end_value
        calendar_event.location = location
        calendar_event.updated_at = app_now()
        db.commit()
        return True, "予定を更新しました。"
    finally:
        db.close()


def delete_calendar_event(user_id, calendar_event_id):
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
                "start_value": format_datetime_local_value(event.start_datetime),
                "end_value": format_datetime_local_value(event.end_datetime),
                "location": event.location,
                "source_label": "PAS"
            })

        return calendar_items
    finally:
        db.close()


def format_calendar_for_prompt(calendar_items):
    if not calendar_items:
        return "PAS Calendarに保存された予定はまだありません。"

    calendar_text = ""

    for event in calendar_items[:20]:
        calendar_text += (
            f"{event['start_text']} - {event['end_text']}: "
            f"{event['title']} 場所:{event['location']}\n"
        )

    return calendar_text


def load_home_snapshot(user_id):
    today_start, today_end = get_today_range()
    next_week_end = today_start + timedelta(days=7)

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

        upcoming_events = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .filter(CalendarEvent.start_datetime >= today_end)
            .filter(CalendarEvent.start_datetime < next_week_end)
            .order_by(CalendarEvent.start_datetime.asc())
            .limit(2)
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
        upcoming_event_items = [
            {
                "title": event.title,
                "time": format_datetime(event.start_datetime),
                "location": event.location
            }
            for event in upcoming_events
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
            daily_message = "今日は進行中の目標を、ひとつだけ前に進める日にしよう。"
        elif timeline_texts:
            daily_message = "今の流れを見ながら、今日の一歩を一緒に決めよう。"
        else:
            daily_message = "今日は何から整える？短くでいいから話してみて。"

        goal_planner_text = "目標ができたら、PASが今日の一歩まで分解します。"

        if goal_items:
            goal_planner_text = f"まずは「{goal_items[0]['title']}」を15分で進む形に分けよう。"

        event_coach_text = "予定を入れると、前日・当日・終了後の振り返りに使えます。"

        if today_event_items:
            event_coach_text = f"今日は「{today_event_items[0]['title']}」の前後で整えよう。"
        elif upcoming_event_items:
            event_coach_text = f"次は「{upcoming_event_items[0]['title']}」。準備と振り返りを残せます。"

        return {
            "daily_message": daily_message,
            "today_events": today_event_items,
            "upcoming_events": upcoming_event_items,
            "active_goals": goal_items,
            "key_memories": memory_items,
            "timeline_items": timeline_texts,
            "pending_memory_count": pending_memory_count,
            "goal_planner_text": goal_planner_text,
            "event_coach_text": event_coach_text
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


def extract_study_memory_from_message(message, subject):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
あなたはStudy PASの学習記憶を整理するAIです。
ユーザーの発言から、今後その人に合わせて教えるために覚える価値がある情報だけを抽出してください。

保存すべき情報:
- 理解度
- 苦手分野
- 得意分野
- 好きな説明方法
- 避けたい説明方法
- 学習目標
- テスト日や提出期限
- 勉強習慣
- 前回の続きに役立つ情報

保存しなくていい情報:
- あいさつ
- その場限りの短い雑談
- 長期的な教え方に関係しない内容

必ずJSONだけで返してください。

保存する情報がある場合:
{{
  "should_save": true,
  "category": "weak_area",
  "content": "ユーザーはPythonのreturnの使い方がまだ曖昧。",
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

category は understanding, weak_area, strong_area, explanation_preference, learning_goal, test_deadline, assignment_deadline, study_habit の中から選んでください。
content は「{subject}」の学習に役立つ短い1文にしてください。
ユーザーが明言した情報は user_statement、推測は ai_inference にしてください。
推測の場合は confidence を 0.65 以下にしてください。

科目:
{subject}

ユーザーの発言:
{message}
"""
    )

    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "should_save": False,
            "category": "",
            "content": "",
            "importance": 0,
            "confidence": 0,
            "source_type": ""
        }


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
- PASは「世界で一番その人を理解するAI」を目指す、人生に寄り添うパートナーです。
- ChatGPTのような説明役に寄りすぎず、まず会話相手として自然に返してください。
- その場のノリだけで返さず、ユーザーの状況・目標・過去の情報を踏まえて返してください。
- まず会話として自然に返してください。説明文・レポート・箇条書きに寄りすぎないでください。
- ユーザーの発言が軽い時は自然に短く返してください。
- 返信の最初の1文は、相づち・共感・結論のどれかにしてください。前置きは不要です。
- 決めつけは避け、情報が足りない時は質問してください。
- アドバイスより先に、共感か確認質問を優先してください。
- 1回の返信で質問は原則1つだけにしてください。
- 短い発言には短く返してください。短い雑談に長文で返すのは禁止です。
- ユーザーに「Goal Plannerを開く」「Memoryを編集する」などの操作をすぐ求めないでください。
- 普通の会話の中から、目標・予定・感情・価値観・重要な出来事を理解する姿勢で返してください。
- PASの価値は機能数ではなく、ユーザーを長期的に理解し続けることにあります。

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


STUDY_TEACHER_RULES = """
Study PASの基本方針:
- あなたは「優しい先生」です。友達、厳しい先生、コーチ、秘書にはなりません。
- 目的は、答えを出すことではなく、ユーザーが理解できるように教え方を育てることです。
- 返答は短めに始めてください。必要な時だけ詳しく説明してください。
- まず状況を受け止め、次に1つだけ確認質問をしてください。
- 説明が必要な時は、結論、たとえ、短い例、理解確認の順にしてください。
- 分からないと言われた時は、言い換え・具体例・小さいステップに分けてください。
- ユーザーの苦手、理解度、好きな説明方法、前回の続き、テスト日、提出期限を自然に使ってください。
- 「前にこの科目をやった日」「久しぶりかどうか」「テストまでの日数」が分かる時は、自然に学習ペースへ反映してください。
- 勉強以外の人生相談、健康管理、日記、予定管理、Goal Plannerの話へ広げすぎないでください。
- 最後は必要に応じて「ここまで分かる？」のような理解確認を1つだけ入れてください。
"""



def build_thread_prompt(thread_title, thread_type):
    if thread_type == DIARY_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットは日記チャットです。
ユーザーの感情や出来事を受け止めることを優先してください。
ユーザーが明確にアドバイスを求めていない場合、すぐに解決策を押しつけず、共感と短い質問を中心にしてください。
"""

    if thread_type == WORK_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットはWork PASです。
就活・面接・ES・キャリア設計を支援してください。
Core Memory、目標、Timeline、Calendarから、今の状況に合う次の一歩を出してください。
"""

    if thread_type == STUDY_THREAD_TYPE:
        return f"""
現在の科目: {thread_title}
このチャットはStudy PASの科目別チャットです。
あなたは「{thread_title}」専門の優しい先生です。
この科目の理解度、苦手、前回の続き、テストや提出期限を踏まえて教えてください。
ただし、全科目で共有しているMemoryから「このユーザーに合う教え方」は活用してください。
"""

    if thread_type == FITNESS_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットはFitness PASです。
筋トレ・食事・睡眠・継続を支援してください。
無理な追い込みではなく、生活状況に合わせた現実的な提案をしてください。
"""

    if thread_type == MENTAL_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットはMental PASです。
感情整理・ストレス・不安・自己理解を支援してください。
診断や断定は避け、安心して話せる短い返答を優先してください。
"""

    if thread_type == FINANCE_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットはFinance PASです。
家計・貯金・支出・将来設計を支援してください。
リスクのある金融助言は断定せず、整理と行動の小さな一歩を中心にしてください。
"""

    if thread_type == HEALTH_THREAD_TYPE:
        return f"""
現在のチャット: {thread_title}
このチャットはHealth PASです。
体調・睡眠・生活習慣・通院予定の整理を支援してください。
医療判断の断定は避け、必要な場合は専門家への相談を促しながら、生活の小さな改善に落とし込んでください。
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

    if thread_type == STUDY_THREAD_TYPE:
        return mode_prompts[mode] + """
Study PASなので、勉強に集中した返答にしてください。
説明が必要な時は、結論→短い例→理解確認の順番にしてください。
長い講義より、ユーザーが次に答えられる小さい質問を1つ出してください。
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
    thread_type=DIARY_THREAD_TYPE,
    study_context_text=""
):
    length_prompt = RESPONSE_LENGTH_PROMPTS.get(response_length, RESPONSE_LENGTH_PROMPTS["balanced"])
    response_style_prompt = build_response_style_prompt(message, response_length, thread_type)
    thread_prompt = build_thread_prompt(thread_title, thread_type)
    current_datetime_text = format_current_datetime_for_prompt()

    if thread_type == STUDY_THREAD_TYPE:
        return f"""
あなたはStudy PASです。

先生としてのルール:
{STUDY_TEACHER_RULES}

現在日時:
{current_datetime_text}

日付の扱い:
「今日」「明日」「昨日」「来週」などは、必ず上の現在日時とタイムゾーンを基準に判断してください。
学習日、テスト日、提出期限が関係する場合は、必要に応じて具体的な日付も添えてください。

チャットの種類:
{thread_prompt}

学習状況:
{study_context_text}

返答の長さ:
{length_prompt}

今回の返し方:
{response_style_prompt}

共有Memory:
{memories}

Timeline Memory:
{timeline_text}

これまでの会話:
{history}

ユーザーの今回の発言:
{message}
"""

    persona_prompt = PAS_PERSONAS.get(persona, PAS_PERSONAS["friend"])

    return f"""
{persona_prompt}

PASの返答ルール:
{PAS_RESPONSE_RULES}

現在日時:
{current_datetime_text}

日付の扱い:
「今日」「明日」「昨日」「来週」などの相対日付は、必ず上の現在日時とタイムゾーンを基準に判断してください。
日付が関係する返答では、必要に応じて具体的な日付も添えてください。

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

PAS Calendar予定:
{calendar_text}

これまでの会話:
{history}

ユーザーの今回の発言:
{message}
"""


def serialize_chat_items(chat_items):
    return [
        {
            "role": chat["role"],
            "content": chat["content"],
            "created_at": format_datetime(chat.get("created_at"))
        }
        for chat in chat_items
    ]


def serialize_thread(thread):
    thread_data = {
        "id": thread.id,
        "title": thread.title,
        "description": get_thread_description(thread.thread_type),
        "thread_type": thread.thread_type,
        "thread_type_label": get_thread_type_label(thread.thread_type),
        "can_delete": thread.thread_type != DIARY_THREAD_TYPE
    }

    if thread.thread_type == STUDY_THREAD_TYPE:
        thread_data["study_context"] = serialize_study_context(thread)

    return thread_data


def process_chat_message(thread, user_id, clean_message):
    is_study_thread = thread.thread_type == STUDY_THREAD_TYPE
    history = load_messages(thread.id, user_id)
    memories = load_memories(user_id)
    timeline_items = load_timeline_items(user_id)
    timeline_text = format_timeline_for_prompt(timeline_items)
    calendar_items = load_calendar_events(user_id)
    calendar_text = format_calendar_for_prompt(calendar_items)
    profile = load_profile(user_id)
    profile_text = format_profile_for_prompt(profile)
    goals = load_goals(user_id)
    goals_text = format_goals_for_prompt(goals)
    settings = load_settings(user_id)
    persona = settings.default_persona
    response_length = settings.response_length

    save_message("user", clean_message, thread.id, user_id)

    if is_study_thread:
        update_study_schedule_from_message(thread.id, user_id, clean_message)
        record_study_activity(thread.id, user_id)
        thread = load_chat_thread(thread.id, user_id) or thread
        response_length = "auto"

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
            if is_study_thread:
                memory_data = extract_study_memory_from_message(clean_message, thread.title)
            else:
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
            user_id=user_id
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
                thread.thread_type,
                format_study_context_for_prompt(thread) if is_study_thread else ""
            )
        )

        ai_message = response.output_text
    except Exception:
        ai_message = "PASの回答を生成できませんでした。もう一度送信してください。"
        should_save_ai_message = False

    if should_save_ai_message:
        save_message("assistant", ai_message, thread.id, user_id)

    chat_items = load_chat_items(thread.id, user_id)

    if not should_save_ai_message:
        chat_items.append({
            "role": "assistant",
            "content": ai_message,
            "created_at": app_now()
        })

    return chat_items


def process_study_image_message(thread, user_id, clean_message, image_bytes, content_type):
    is_study_thread = thread.thread_type == STUDY_THREAD_TYPE
    prompt_message = clean_message or "この画像の内容を読み取って、分かりやすく授業してください。"
    user_message = f"[画像] {prompt_message}"

    save_message("user", user_message, thread.id, user_id)

    if is_study_thread:
        update_study_schedule_from_message(thread.id, user_id, prompt_message)
        record_study_activity(thread.id, user_id)
        thread = load_chat_thread(thread.id, user_id) or thread

    history = load_messages(thread.id, user_id)
    memories = load_memories(user_id)
    timeline_text = format_timeline_for_prompt(load_timeline_items(user_id))
    study_context_text = format_study_context_for_prompt(thread) if is_study_thread else ""
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_url = f"data:{content_type};base64,{encoded_image}"

    ai_message = ""
    should_save_ai_message = True

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_ai_prompt(
                                prompt_message,
                                history,
                                memories,
                                timeline_text,
                                "Study PAS v1.0ではGoogle Calendarは使いません。",
                                "Study PAS v1.0ではプロフィール入力より会話からの理解を優先します。",
                                "Study PAS v1.0ではGoal Plannerは使いません。",
                                "friend",
                                "auto",
                                thread.title,
                                thread.thread_type,
                                study_context_text
                            ) + "\n\n画像の内容を読み取り、必要なら問題文を整理してから教えてください。"
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url
                        }
                    ]
                }
            ]
        )
        ai_message = response.output_text
    except Exception:
        ai_message = "画像を読み取れませんでした。もう一度送るか、画像の内容を短く文章で教えてください。"
        should_save_ai_message = False

    if should_save_ai_message:
        save_message("assistant", ai_message, thread.id, user_id)

    chat_items = load_chat_items(thread.id, user_id)

    if not should_save_ai_message:
        chat_items.append({
            "role": "assistant",
            "content": ai_message,
            "created_at": app_now()
        })

    return chat_items


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


def render_react_app(request, current_user):
    settings = load_settings(current_user.id)

    response = templates.TemplateResponse(
        request=request,
        name="react_app.html",
        context={
            "settings": settings,
            "current_user": current_user,
            "asset_version": ASSET_VERSION
        }
    )

    response.headers["Cache-Control"] = "no-store"
    return response


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


@app.get("/api/home")
def api_home(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    settings = load_settings(current_user.id)
    study_threads = load_study_threads(current_user.id)

    return {
        "app_title": "Study PAS",
        "app_concept": "一人ひとりを理解し、教え方が成長していく先生。",
        "subject_examples": SUBJECT_EXAMPLES,
        "user": {
            "id": current_user.id,
            "name": current_user.name
        },
        "settings": {
            "theme_name": settings.theme_name,
            "default_persona": settings.default_persona,
            "response_length": settings.response_length
        },
        "study_threads": study_threads
    }


@app.get("/api/chat")
def api_diary_chat(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    settings = load_settings(current_user.id)
    study_thread = get_or_create_default_study_thread(current_user.id)
    chat_items = load_chat_items(study_thread.id, current_user.id)

    return {
        "settings": {
            "theme_name": settings.theme_name,
            "default_persona": settings.default_persona
        },
        "thread": serialize_thread(study_thread),
        "messages": serialize_chat_items(chat_items)
    }


@app.get("/api/chat/{thread_id}")
def api_chat_thread(request: Request, thread_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    settings = load_settings(current_user.id)
    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return JSONResponse({"error": "thread_not_found"}, status_code=404)

    if thread.thread_type != STUDY_THREAD_TYPE:
        return JSONResponse({"error": "study_thread_required"}, status_code=404)

    chat_items = load_chat_items(thread.id, current_user.id)

    return {
        "settings": {
            "theme_name": settings.theme_name,
            "default_persona": settings.default_persona
        },
        "thread": serialize_thread(thread),
        "messages": serialize_chat_items(chat_items)
    }


@app.post("/api/chat_threads")
def api_chat_thread_create(request: Request, payload: ChatThreadCreatePayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    clean_title = normalize_subject_title(payload.title)

    if not clean_title:
        clean_title = "新しい学習"

    thread = create_chat_thread(clean_title, current_user.id, STUDY_THREAD_TYPE)

    if thread is None:
        return JSONResponse({"error": "thread_create_failed"}, status_code=400)

    return {
        "thread": serialize_thread(thread),
        "url": f"/chat/{thread.id}"
    }


@app.post("/api/chat/{thread_id}/messages")
def api_chat_message_create(request: Request, thread_id: int, payload: ChatMessageCreatePayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return JSONResponse({"error": "thread_not_found"}, status_code=404)

    if thread.thread_type != STUDY_THREAD_TYPE:
        return JSONResponse({"error": "study_thread_required"}, status_code=400)

    clean_message = payload.message.strip()

    if not clean_message:
        return JSONResponse({"error": "message_required"}, status_code=400)

    chat_items = process_chat_message(thread, current_user.id, clean_message)
    thread = load_chat_thread(thread.id, current_user.id) or thread

    return {
        "thread": serialize_thread(thread),
        "messages": serialize_chat_items(chat_items)
    }


@app.post("/api/chat/{thread_id}/image")
async def api_chat_image_upload(
    request: Request,
    thread_id: int,
    message: str = Form(""),
    image: UploadFile = File(...)
):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return JSONResponse({"error": "thread_not_found"}, status_code=404)

    if thread.thread_type != STUDY_THREAD_TYPE:
        return JSONResponse({"error": "study_thread_required"}, status_code=400)

    content_type = image.content_type or ""

    if not content_type.startswith("image/"):
        return JSONResponse({"error": "image_required"}, status_code=400)

    image_bytes = await image.read()

    if not image_bytes:
        return JSONResponse({"error": "image_required"}, status_code=400)

    if len(image_bytes) > STUDY_IMAGE_MAX_BYTES:
        return JSONResponse({"error": "image_too_large"}, status_code=400)

    clean_message = message.strip()
    chat_items = process_study_image_message(thread, current_user.id, clean_message, image_bytes, content_type)
    thread = load_chat_thread(thread.id, current_user.id) or thread

    return {
        "thread": serialize_thread(thread),
        "messages": serialize_chat_items(chat_items)
    }


@app.delete("/api/chat_threads/{thread_id}")
def api_chat_thread_delete(request: Request, thread_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    delete_chat_thread(thread_id, current_user.id)
    return {"ok": True}


@app.get("/")
def home(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return render_react_app(request, current_user)

@app.get("/chat")
def chat_page(request: Request, draft: str = ""):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    get_or_create_default_study_thread(current_user.id)
    return render_react_app(request, current_user)

@app.get("/chat/{thread_id}")
def chat_thread_page(request: Request, thread_id: int, draft: str = ""):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return RedirectResponse(url="/", status_code=303)

    return render_react_app(request, current_user)

@app.post("/chat_threads")
def chat_thread_create(
    request: Request,
    title: str = Form(""),
    thread_type: str = Form(STUDY_THREAD_TYPE)
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    clean_title = title.strip()

    if not clean_title:
        return RedirectResponse(url="/", status_code=303)

    thread = create_chat_thread(clean_title, current_user.id, STUDY_THREAD_TYPE)

    if thread is None:
        return RedirectResponse(url="/", status_code=303)

    return RedirectResponse(url=f"/chat/{thread.id}", status_code=303)


@app.post("/specialist_threads")
def specialist_thread_create(request: Request, thread_type: str = Form(CUSTOM_THREAD_TYPE)):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    if thread_type not in SPECIALIST_THREAD_TYPES:
        return RedirectResponse(url="/", status_code=303)

    thread = create_chat_thread(
        title=get_specialist_thread_title(thread_type),
        user_id=current_user.id,
        thread_type=thread_type
    )

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
    calendar_items = load_calendar_events(current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "settings": settings,
            "calendar_items": calendar_items,
            "message": request.query_params.get("message", "")
        }
    )


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

    _, message = create_calendar_event(
        user_id=current_user.id,
        title=title,
        description=description,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        location=location
    )

    return RedirectResponse(url=f"/calendar?message={quote(message)}", status_code=303)


@app.post("/calendar/events/{calendar_event_id}/edit")
def calendar_event_edit(
    request: Request,
    calendar_event_id: int,
    title: str = Form(""),
    description: str = Form(""),
    start_datetime: str = Form(""),
    end_datetime: str = Form(""),
    location: str = Form("")
):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    _, message = update_calendar_event(
        user_id=current_user.id,
        calendar_event_id=calendar_event_id,
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

    _, message = delete_calendar_event(current_user.id, calendar_event_id)
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

    settings = load_settings(current_user.id)
    chat_items = process_chat_message(thread, current_user.id, clean_message)

    
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
            "can_delete_thread": thread.thread_type != DIARY_THREAD_TYPE
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
