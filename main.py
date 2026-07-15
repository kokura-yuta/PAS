from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
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
import smtplib
from email.message import EmailMessage
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
ASSET_VERSION = (os.getenv("RENDER_GIT_COMMIT") or "study-20260715-1")[:12]
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
ROADMAP_STATUSES = ["learned", "learning", "review", "not_started", "skipped"]
ROADMAP_STATUS_LABELS = {
    "learned": "理解済み",
    "learning": "学習中",
    "review": "復習",
    "not_started": "未学習",
    "skipped": "飛ばした単元"
}
ROADMAP_FOLLOW_WORDS = [
    "ロードマップ通り",
    "ロードマップどおり",
    "おすすめ通り",
    "おすすめどおり",
    "順番通り",
    "順番どおり"
]
ROADMAP_SKIP_WORDS = [
    "飛ばす",
    "飛ばして",
    "飛ばした",
    "スキップ",
    "ここは飛ば",
    "この単元は飛ば"
]
ROADMAP_CREATE_WORDS = [
    "作成",
    "作って",
    "作る",
    "作りたい",
    "作ろう"
]
LESSON_LEVEL_ORDER = [
    "term",
    "short_answer",
    "code_reading",
    "code_fix",
    "code_creation",
    "mini_app"
]
LESSON_LEVEL_LABELS = {
    "term": "用語確認",
    "short_answer": "記述問題",
    "code_reading": "コード読解",
    "code_fix": "コード修正",
    "code_creation": "コード作成",
    "mini_app": "ミニアプリ制作"
}
LESSON_UNDERSTOOD_WORDS = [
    "わかった",
    "分かった",
    "理解した",
    "できた",
    "いけた",
    "正解",
    "なるほど"
]
STUDY_IMAGE_MAX_BYTES = 7 * 1024 * 1024
STUDY_MEMORY_CATEGORIES = {
    "understanding",
    "weak_area",
    "strong_area",
    "explanation_preference",
    "learning_goal",
    "test_deadline",
    "assignment_deadline",
    "study_habit",
    "lesson_report",
    "next_step"
}
STUDY_CONFUSION_WORDS = [
    "わからない",
    "分からない",
    "わかんない",
    "分かんない",
    "理解できない",
    "理解できてない",
    "むずい",
    "難しい",
    "曖昧",
    "あいまい",
    "つまず",
    "できない",
    "エラー",
    "意味が分から"
]
STUDY_LESSON_END_WORDS = [
    "今日はここまで",
    "ここまでにします",
    "今日のまとめ",
    "学習レポート",
    "次回やること"
]


class ChatThreadCreatePayload(BaseModel):
    title: str = ""
    thread_type: str = CUSTOM_THREAD_TYPE


class ChatMessageCreatePayload(BaseModel):
    message: str = ""


class RoadmapDeletePayload(BaseModel):
    subject: str = ""
    thread_id: int | None = None


class TextbookPreviewPayload(BaseModel):
    source_note: str = ""


class TextbookConfirmPayload(BaseModel):
    thread_id: int
    mode: str = "create"
    target_textbook_id: int | None = None
    title: str = ""
    bookshelf_subject: str = ""
    introduction: str = ""
    learning_image: str = ""
    beginner_explanation: str = ""
    visual_diagram: str = ""
    code_example: str = ""
    code_walkthrough: str = ""
    personal_points: str = ""
    basic_explanation: str = ""
    concrete_examples: str = ""
    key_points: str = ""
    weak_points: str = ""
    unclear_points: str = ""
    common_mistakes: str = ""
    check_questions: str = ""
    application_questions: str = ""
    model_answers: str = ""
    detailed_explanations: str = ""
    related_textbooks: str = ""
    update_summary: str = ""


class TextbookAnswerPayload(BaseModel):
    answer_type: str = "check"
    answer_text: str = ""
    used_hint: bool = False


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


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    token_hash = Column(Text, unique=True, index=True)
    expires_at = Column(DateTime)
    used_at = Column(DateTime)
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


class StudyTextbook(Base):
    __tablename__ = "study_textbooks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    title = Column(String(255))
    introduction = Column(Text)
    learning_image = Column(Text)
    beginner_explanation = Column(Text)
    visual_diagram = Column(Text)
    code_example = Column(Text)
    code_walkthrough = Column(Text)
    personal_points = Column(Text)
    basic_explanation = Column(Text)
    concrete_examples = Column(Text)
    key_points = Column(Text)
    weak_points = Column(Text)
    unclear_points = Column(Text)
    common_mistakes = Column(Text)
    check_questions = Column(Text)
    application_questions = Column(Text)
    model_answers = Column(Text)
    detailed_explanations = Column(Text)
    related_textbooks = Column(Text)
    created_at = Column(DateTime, default=app_now)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class StudyTextbookUpdate(Base):
    __tablename__ = "study_textbook_updates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    textbook_id = Column(Integer, index=True)
    action_type = Column(String(50), default="created")
    summary = Column(Text)
    created_at = Column(DateTime, default=app_now)


class StudyUnderstanding(Base):
    __tablename__ = "study_understandings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    textbook_id = Column(Integer, index=True)
    scope_type = Column(String(50), index=True)
    item_name = Column(String(255))
    percent = Column(Integer, default=0)
    previous_percent = Column(Integer, default=0)
    delta_percent = Column(Integer, default=0)
    evidence = Column(Text)
    last_assessed_at = Column(DateTime)
    next_review_at = Column(DateTime)
    review_interval_days = Column(Integer, default=1)
    review_count = Column(Integer, default=0)
    retention_level = Column(String(50), default="new")
    created_at = Column(DateTime, default=app_now)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class StudyAssessment(Base):
    __tablename__ = "study_assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    textbook_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    answer_type = Column(String(50), default="check")
    answer_text = Column(Text)
    feedback = Column(Text)
    score_percent = Column(Integer, default=0)
    understood_points = Column(Text)
    weak_points = Column(Text)
    unclear_points = Column(Text)
    thinking_gap = Column(Text)
    next_review_content = Column(Text)
    next_review_at = Column(DateTime)
    review_interval_days = Column(Integer, default=1)
    used_hint = Column(Boolean, default=False)
    created_at = Column(DateTime, default=app_now)


class StudyRoadmapItem(Base):
    __tablename__ = "study_roadmap_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    title = Column(String(255))
    status = Column(String(50), default="not_started")
    reason = Column(Text)
    sort_order = Column(Integer, default=0)
    source_type = Column(String(50), default="ai")
    created_at = Column(DateTime, default=app_now)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class StudyRoadmapDeletion(Base):
    __tablename__ = "study_roadmap_deletions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    deleted_goal = Column(Text)
    created_at = Column(DateTime, default=app_now)


class StudyLessonState(Base):
    __tablename__ = "study_lesson_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(Integer, index=True)
    subject = Column(String(100), index=True)
    live_understanding = Column(Integer, default=35)
    question_level = Column(String(50), default="term")
    current_focus = Column(String(255))
    mastered_points = Column(Text)
    weak_points = Column(Text)
    recent_problem_history = Column(Text)
    last_signal = Column(Text)
    created_at = Column(DateTime, default=app_now)
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
        "calendar_events",
        "study_textbooks",
        "study_textbook_updates",
        "study_understandings",
        "study_assessments",
        "study_roadmap_items",
        "study_roadmap_deletions",
        "study_lesson_states",
        "password_reset_tokens"
    ]

    for table_name in user_tables:
        ensure_columns(table_name, {"user_id": "INTEGER"})


ensure_user_id_columns()

def ensure_study_textbook_chapter_columns():
    ensure_columns(
        "study_textbooks",
        {
            "introduction": "TEXT",
            "learning_image": "TEXT",
            "beginner_explanation": "TEXT",
            "visual_diagram": "TEXT",
            "code_example": "TEXT",
            "code_walkthrough": "TEXT",
            "personal_points": "TEXT"
        }
    )


ensure_study_textbook_chapter_columns()

def ensure_study_learning_columns():
    ensure_columns(
        "study_understandings",
        {
            "next_review_at": "TIMESTAMP",
            "review_interval_days": "INTEGER DEFAULT 1",
            "review_count": "INTEGER DEFAULT 0",
            "retention_level": "VARCHAR(50) DEFAULT 'new'"
        }
    )
    ensure_columns(
        "study_assessments",
        {
            "next_review_at": "TIMESTAMP",
            "review_interval_days": "INTEGER DEFAULT 1"
        }
    )


ensure_study_learning_columns()


def ensure_study_roadmap_columns():
    ensure_columns(
        "study_roadmap_items",
        {
            "thread_id": "INTEGER"
        }
    )


ensure_study_roadmap_columns()


def ensure_study_lesson_state_columns():
    ensure_columns(
        "study_lesson_states",
        {
            "thread_id": "INTEGER",
            "subject": "VARCHAR(100)",
            "live_understanding": "INTEGER DEFAULT 35",
            "question_level": "VARCHAR(50) DEFAULT 'term'",
            "current_focus": "VARCHAR(255)",
            "mastered_points": "TEXT",
            "weak_points": "TEXT",
            "recent_problem_history": "TEXT",
            "last_signal": "TEXT",
            "updated_at": "TIMESTAMP"
        }
    )


ensure_study_lesson_state_columns()

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


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_base_url(request):
    configured_url = (os.getenv("APP_BASE_URL") or "").strip()

    if configured_url:
        return configured_url.rstrip("/")

    return str(request.base_url).rstrip("/")


def create_password_reset_token(email):
    clean_email = normalize_email(email)

    if not clean_email:
        return None

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.email == clean_email).first()

        if user is None:
            return None

        token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(token),
            expires_at=app_now() + timedelta(minutes=45)
        )

        db.add(reset_token)
        db.commit()
        return token
    finally:
        db.close()


def load_valid_password_reset_token(token):
    token = (token or "").strip()

    if not token:
        return None

    db = SessionLocal()

    try:
        reset_token = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.token_hash == hash_reset_token(token))
            .filter(PasswordResetToken.used_at.is_(None))
            .first()
        )

        if reset_token is None:
            return None

        if reset_token.expires_at is None or reset_token.expires_at < app_now():
            return None

        user = db.query(User).filter(User.id == reset_token.user_id).first()

        if user is None:
            return None

        return {
            "id": reset_token.id,
            "user_id": user.id,
            "email": user.email
        }
    finally:
        db.close()


def reset_user_password(token, password):
    if len(password or "") < PASSWORD_MIN_LENGTH:
        return False

    token_data = load_valid_password_reset_token(token)

    if token_data is None:
        return False

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.id == token_data["user_id"]).first()
        reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.id == token_data["id"]).first()

        if user is None or reset_token is None or reset_token.used_at is not None:
            return False

        user.password_hash = hash_password(password)
        reset_token.used_at = app_now()
        db.commit()
        return True
    finally:
        db.close()


def send_password_reset_email(email, reset_url):
    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = (os.getenv("SMTP_USERNAME") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or os.getenv("EMAIL_FROM") or smtp_username or "").strip()

    if not smtp_host or not smtp_from:
        return False

    message = EmailMessage()
    message["Subject"] = "Study PAS パスワード再設定"
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(
        "Study PASのパスワード再設定リンクです。\n\n"
        f"{reset_url}\n\n"
        "このリンクは45分で使えなくなります。心当たりがない場合は、このメールを無視してください。"
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as smtp:
            smtp.starttls()

            if smtp_username and smtp_password:
                smtp.login(smtp_username, smtp_password)

            smtp.send_message(message)
        return True
    except Exception:
        return False


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
        "calendar_events",
        "study_textbooks",
        "study_textbook_updates",
        "study_understandings",
        "study_assessments",
        "study_roadmap_items",
        "study_roadmap_deletions",
        "study_lesson_states"
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


def format_study_day_label(days_since_last):
    if days_since_last is None:
        return "未学習"

    if days_since_last == 0:
        return "今日"

    if days_since_last == 1:
        return "昨日"

    return f"{days_since_last}日前"


def contains_any_word(text, words):
    text = (text or "").strip()
    return any(word in text for word in words)


def should_make_study_weak_note(message):
    return contains_any_word(message, STUDY_CONFUSION_WORDS)


def is_study_lesson_end_message(message):
    return contains_any_word(message, STUDY_LESSON_END_WORDS)


def is_study_summary_action(message):
    return "理解確認" in (message or "") or "応用問題" in (message or "")


def build_next_lesson_label(latest_user_message):
    if latest_user_message is None:
        return "最初の授業を始める"

    content = (latest_user_message.content or "").replace("[画像]", "").strip()

    if not content:
        return "前回の続きから始める"

    if is_study_lesson_end_message(content):
        return "前回のまとめを確認して再開する"

    if "理解確認" in content:
        return "前回の理解確認の続き"

    if "応用問題" in content:
        return "前回の応用問題の続き"

    if "画像" in (latest_user_message.content or ""):
        return "前回の画像問題の続き"

    return f"{truncate_text(content, 28)} の続き"


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
            latest_user_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id)
                .filter(ChatMessage.thread_id == thread.id)
                .filter(ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.desc())
                .first()
            )
            study_context = serialize_study_context(thread)

            study_threads.append({
                "id": thread.id,
                "title": thread.title,
                "display_title": truncate_text(thread.title, THREAD_TITLE_MAX_LENGTH),
                "latest_message": truncate_text(
                    latest_message.content if latest_message else "まだ授業は始まっていません。",
                    64
                ),
                "updated_at_text": format_datetime(thread.updated_at or thread.created_at),
                "next_lesson_label": build_next_lesson_label(latest_user_message),
                "study_context": study_context,
                "can_delete": True
            })

        return study_threads
    finally:
        db.close()


def load_recent_study_history(user_id, limit=5):
    db = SessionLocal()

    try:
        threads = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .filter(ChatThread.last_studied_at.isnot(None))
            .order_by(ChatThread.last_studied_at.desc())
            .limit(limit)
            .all()
        )

        history_items = []

        for thread in threads:
            latest_user_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id)
                .filter(ChatMessage.thread_id == thread.id)
                .filter(ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.desc())
                .first()
            )
            context = serialize_study_context(thread)

            history_items.append({
                "id": thread.id,
                "title": thread.title,
                "day_label": format_study_day_label(context["days_since_last"]),
                "summary": build_next_lesson_label(latest_user_message),
                "url": f"/chat/{thread.id}"
            })

        return history_items
    finally:
        db.close()


def load_study_memory_highlights(user_id, limit=4):
    db = SessionLocal()

    try:
        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .filter(Memory.is_active.is_(True))
            .filter(or_(Memory.status == "confirmed", Memory.status.is_(None)))
            .filter(Memory.category.in_(STUDY_MEMORY_CATEGORIES))
            .order_by(
                Memory.importance.desc(),
                Memory.confidence.desc(),
                Memory.created_at.desc()
            )
            .limit(limit)
            .all()
        )

        return [
            {
                "id": memory.id,
                "category": memory.category,
                "content": memory.content
            }
            for memory in memories
        ]
    finally:
        db.close()


TEXTBOOK_CONTENT_FIELDS = [
    "introduction",
    "learning_image",
    "beginner_explanation",
    "visual_diagram",
    "code_example",
    "code_walkthrough",
    "basic_explanation",
    "concrete_examples",
    "key_points",
    "personal_points",
    "weak_points",
    "unclear_points",
    "common_mistakes",
    "check_questions",
    "application_questions",
    "model_answers",
    "detailed_explanations",
    "related_textbooks"
]


TEXTBOOK_FIELD_LABELS = {
    "introduction": "導入",
    "learning_image": "イメージ",
    "beginner_explanation": "基本説明",
    "visual_diagram": "図・流れ",
    "code_example": "実際のコード・実例",
    "code_walkthrough": "コード解説・流れ",
    "basic_explanation": "補足説明",
    "concrete_examples": "補足の具体例",
    "key_points": "ここだけは覚えよう",
    "personal_points": "あなた専用ポイント",
    "weak_points": "本人が苦手だったポイント",
    "unclear_points": "まだ曖昧な内容",
    "common_mistakes": "本人が間違えやすいポイント",
    "check_questions": "理解確認問題5問",
    "application_questions": "応用問題10問",
    "model_answers": "模範解答",
    "detailed_explanations": "詳しい解説",
    "related_textbooks": "関連する教科書"
}


def serialize_textbook_summary(textbook):
    return {
        "id": textbook.id,
        "title": textbook.title,
        "subject": textbook.subject,
        "created_at": format_date(textbook.created_at),
        "updated_at": format_date(textbook.updated_at),
        "url": f"/textbook/{textbook.id}"
    }


def serialize_textbook_update(update):
    return {
        "id": update.id,
        "action_type": update.action_type,
        "summary": update.summary,
        "created_at": format_date(update.created_at)
    }


def serialize_understanding(understanding):
    next_review_at = understanding.next_review_at
    review_due = bool(next_review_at and next_review_at.date() <= app_now().date())

    return {
        "id": understanding.id,
        "subject": understanding.subject,
        "scope_type": understanding.scope_type,
        "item_name": understanding.item_name,
        "percent": understanding.percent or 0,
        "previous_percent": understanding.previous_percent or 0,
        "delta_percent": understanding.delta_percent or 0,
        "evidence": understanding.evidence or "",
        "last_assessed_at": format_datetime(understanding.last_assessed_at),
        "next_review_at": format_date(next_review_at),
        "review_interval_days": understanding.review_interval_days or 1,
        "review_count": understanding.review_count or 0,
        "retention_level": understanding.retention_level or "new",
        "review_due": review_due
    }


def serialize_assessment(assessment):
    return {
        "id": assessment.id,
        "answer_type": assessment.answer_type,
        "answer_text": assessment.answer_text or "",
        "feedback": assessment.feedback or "",
        "score_percent": assessment.score_percent or 0,
        "understood_points": assessment.understood_points or "",
        "weak_points": assessment.weak_points or "",
        "unclear_points": assessment.unclear_points or "",
        "thinking_gap": assessment.thinking_gap or "",
        "next_review_content": assessment.next_review_content or "",
        "next_review_at": format_date(assessment.next_review_at),
        "review_interval_days": assessment.review_interval_days or 1,
        "used_hint": bool(assessment.used_hint),
        "created_at": format_datetime(assessment.created_at)
    }


def serialize_roadmap_item(item):
    return {
        "id": item.id,
        "thread_id": item.thread_id,
        "subject": item.subject,
        "title": item.title or "",
        "status": item.status or "not_started",
        "reason": item.reason or "",
        "sort_order": item.sort_order or 0
    }


def build_review_suggestions(understandings, limit=4):
    today = app_now().date()
    suggestions = []

    for item in understandings or []:
        if item.scope_type not in ["textbook", "item"]:
            continue

        if not item.next_review_at:
            continue

        days_until = (item.next_review_at.date() - today).days

        if days_until > 3:
            continue

        suggestions.append({
            **serialize_understanding(item),
            "days_until_review": days_until,
            "review_message": "今日復習するとよさそうです。" if days_until <= 0 else f"{days_until}日後に復習予定です。"
        })

    return sorted(
        suggestions,
        key=lambda item: (item["days_until_review"], item["percent"])
    )[:limit]


def serialize_textbook_detail(textbook, updates=None, understandings=None, assessments=None):
    sections = [
        {
            "key": field_name,
            "label": TEXTBOOK_FIELD_LABELS[field_name],
            "content": getattr(textbook, field_name) or ""
        }
        for field_name in TEXTBOOK_CONTENT_FIELDS
    ]

    return {
        **serialize_textbook_summary(textbook),
        "thread_id": textbook.thread_id,
        "sections": sections,
        "updates": [
            serialize_textbook_update(update)
            for update in (updates or [])
        ],
        "understandings": [
            serialize_understanding(understanding)
            for understanding in (understandings or [])
        ],
        "assessments": [
            serialize_assessment(assessment)
            for assessment in (assessments or [])
        ],
        "review_suggestions": build_review_suggestions(understandings or [])
    }


def load_textbook(textbook_id, user_id):
    db = SessionLocal()

    try:
        textbook = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.id == textbook_id)
            .filter(StudyTextbook.user_id == user_id)
            .first()
        )

        if textbook is None:
            return None

        updates = (
            db.query(StudyTextbookUpdate)
            .filter(StudyTextbookUpdate.user_id == user_id)
            .filter(StudyTextbookUpdate.textbook_id == textbook.id)
            .order_by(StudyTextbookUpdate.created_at.desc())
            .all()
        )

        understandings = (
            db.query(StudyUnderstanding)
            .filter(StudyUnderstanding.user_id == user_id)
            .filter(
                or_(
                    StudyUnderstanding.textbook_id == textbook.id,
                    StudyUnderstanding.scope_type == "subject"
                )
            )
            .filter(StudyUnderstanding.subject == textbook.subject)
            .order_by(StudyUnderstanding.scope_type.asc(), StudyUnderstanding.updated_at.desc())
            .all()
        )

        assessments = (
            db.query(StudyAssessment)
            .filter(StudyAssessment.user_id == user_id)
            .filter(StudyAssessment.textbook_id == textbook.id)
            .order_by(StudyAssessment.created_at.desc())
            .limit(5)
            .all()
        )

        return serialize_textbook_detail(textbook, updates, understandings, assessments)
    finally:
        db.close()


def load_bookshelves(user_id):
    db = SessionLocal()

    try:
        subjects = {}

        study_threads = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .all()
        )

        for thread in study_threads:
            subject = thread.title or "学習相談"
            subjects[subject] = {
                "subject": subject,
                "textbook_count": 0,
                "latest_updated_at": thread.updated_at or thread.created_at,
                "url": f"/bookshelf/{quote(subject)}"
            }

        textbooks = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.user_id == user_id)
            .order_by(StudyTextbook.updated_at.desc().nullslast(), StudyTextbook.created_at.desc())
            .all()
        )

        for textbook in textbooks:
            subject = textbook.subject or "学習相談"
            if subject not in subjects:
                subjects[subject] = {
                    "subject": subject,
                    "textbook_count": 0,
                    "latest_updated_at": textbook.updated_at or textbook.created_at,
                    "url": f"/bookshelf/{quote(subject)}"
                }

            subjects[subject]["textbook_count"] += 1
            latest = subjects[subject]["latest_updated_at"]
            textbook_updated = textbook.updated_at or textbook.created_at
            if latest is None or (textbook_updated and textbook_updated > latest):
                subjects[subject]["latest_updated_at"] = textbook_updated

        shelves = []

        for shelf in subjects.values():
            shelves.append({
                "subject": shelf["subject"],
                "textbook_count": shelf["textbook_count"],
                "latest_updated_at": format_date(shelf["latest_updated_at"]),
                "url": shelf["url"]
            })

        return sorted(shelves, key=lambda item: item["latest_updated_at"], reverse=True)
    finally:
        db.close()


ROADMAP_TEMPLATES = {
    "Python": ["基本文法", "変数", "条件分岐", "繰り返し", "関数", "引数", "return", "リスト", "辞書", "クラス", "ファイル操作", "Webアプリ基礎"],
    "英語": ["be動詞", "一般動詞", "三人称単数", "現在進行形", "過去形", "未来表現", "助動詞", "比較", "不定詞", "現在完了"],
    "数学": ["計算の基礎", "方程式", "関数", "一次関数", "二次関数", "図形", "確率", "証明"],
    "基本情報": ["コンピュータ基礎", "アルゴリズム", "データ構造", "ネットワーク", "データベース", "セキュリティ", "マネジメント", "ストラテジ"],
    "TOEIC": ["品詞", "時制", "文型", "接続詞", "リスニング基礎", "Part 5", "Part 6", "Part 7"]
}


def normalize_roadmap_status(status):
    return status if status in ROADMAP_STATUSES else "not_started"


def infer_roadmap_status(title, textbooks, understandings):
    title_text = (title or "").lower()
    related_understandings = [
        item
        for item in understandings
        if title_text and title_text in ((item.item_name or "").lower())
    ]

    if related_understandings:
        best = max([normalize_percent(item.percent) for item in related_understandings])
        has_due_review = any(item.next_review_at and item.next_review_at.date() <= app_now().date() for item in related_understandings)

        if has_due_review and best < 95:
            return "review"
        if best >= 85:
            return "learned"
        if best >= 35:
            return "learning"

    for textbook in textbooks:
        combined = f"{textbook.title or ''} {textbook.key_points or ''} {textbook.personal_points or ''}".lower()
        if title_text and title_text in combined:
            return "learning"

    return "not_started"


def get_roadmap_status_label(status):
    return ROADMAP_STATUS_LABELS.get(normalize_roadmap_status(status), "未学習")


def roadmap_deletion_filter(query, thread_id):
    if thread_id is None:
        return query.filter(StudyRoadmapDeletion.thread_id.is_(None))

    return query.filter(
        or_(
            StudyRoadmapDeletion.thread_id == thread_id,
            StudyRoadmapDeletion.thread_id.is_(None)
        )
    )


def is_roadmap_deleted(db, user_id, subject, thread_id=None):
    clean_subject = normalize_subject_title(subject) or "学習相談"
    query = (
        db.query(StudyRoadmapDeletion)
        .filter(StudyRoadmapDeletion.user_id == user_id)
        .filter(StudyRoadmapDeletion.subject == clean_subject)
    )

    return roadmap_deletion_filter(query, thread_id).first() is not None


def clear_roadmap_deletion_marker(db, user_id, subject, thread_id=None):
    clean_subject = normalize_subject_title(subject) or "学習相談"
    query = (
        db.query(StudyRoadmapDeletion)
        .filter(StudyRoadmapDeletion.user_id == user_id)
        .filter(StudyRoadmapDeletion.subject == clean_subject)
    )
    roadmap_deletion_filter(query, thread_id).delete(synchronize_session=False)


def is_roadmap_follow_message(message):
    return contains_any_word(message, ROADMAP_FOLLOW_WORDS)


def is_roadmap_skip_message(message):
    return contains_any_word(message, ROADMAP_SKIP_WORDS)


def is_roadmap_create_message(message):
    text_value = message or ""
    has_roadmap_word = "ロードマップ" in text_value or "学習計画" in text_value
    return has_roadmap_word and contains_any_word(text_value, ROADMAP_CREATE_WORDS)


def choose_roadmap_focus_item(roadmap_items):
    for status in ["learning", "review"]:
        for item in roadmap_items:
            if normalize_roadmap_status(item.status) == status:
                return item

    for item in roadmap_items:
        if normalize_roadmap_status(item.status) == "not_started":
            return item

    return roadmap_items[0] if roadmap_items else None


def find_roadmap_item_from_message(roadmap_items, message):
    message_text = (message or "").lower()

    for item in roadmap_items:
        title = (item.title or "").strip().lower()

        if title and title in message_text:
            return item

    return choose_roadmap_focus_item(roadmap_items)


def apply_roadmap_message_intent(db, roadmap_items, message):
    intent = {
        "type": "",
        "item_title": ""
    }

    if not roadmap_items:
        return intent

    if is_roadmap_skip_message(message):
        item = find_roadmap_item_from_message(roadmap_items, message)

        if item is not None:
            item.status = "skipped"
            item.reason = "ユーザーがこの単元を飛ばすと決めたため、以後は必要な前提だけ補足します。"
            item.source_type = "user"
            item.updated_at = app_now()
            db.commit()
            intent = {
                "type": "skip",
                "item_title": item.title
            }

    elif is_roadmap_follow_message(message):
        item = choose_roadmap_focus_item(roadmap_items)

        if item is not None and normalize_roadmap_status(item.status) == "not_started":
            item.status = "learning"
            item.reason = "ユーザーがロードマップ通りに進むと決めたため、現在の授業位置として開始します。"
            item.source_type = "user"
            item.updated_at = app_now()
            db.commit()

        if item is not None:
            intent = {
                "type": "follow",
                "item_title": item.title
            }

    return intent


def fallback_roadmap_items(subject, textbooks, understandings):
    titles = ROADMAP_TEMPLATES.get(subject)

    if not titles:
        titles = []

    for textbook in textbooks:
        title = truncate_text(textbook.title or "", 40)
        if title and title not in titles:
            titles.append(title)

    if not titles:
        titles = ["基礎の確認", "重要語句の理解", "例題で確認", "自分で説明する", "応用問題"]

    return [
        {
            "title": title,
            "status": infer_roadmap_status(title, textbooks, understandings),
            "reason": "今の理解度と作成済み教科書から、次に進みやすい順番として並べています。"
        }
        for title in titles[:10]
    ]


def generate_roadmap_items_with_ai(subject, textbooks, understandings):
    textbook_titles = [textbook.title for textbook in textbooks if textbook.title]
    understanding_summary = [
        {
            "item": item.item_name,
            "percent": item.percent,
            "scope": item.scope_type
        }
        for item in understandings[:20]
    ]

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=f"""
あなたはStudy PASの学習設計をする先生です。
科目ごとに、ユーザーが理解しやすい学習ロードマップを作ってください。

ルール:
- 6〜10個の単元にする。
- 順番はおすすめだが、強制しない。
- status は learned / learning / review / not_started / skipped のどれか。
- 既に教科書や理解度がある内容は反映する。
- 前提知識を飛ばしそうな場合は reason でやさしく説明する。
- 必ずJSONだけで返す。

返答形式:
{{
  "items": [
    {{"title": "関数", "status": "learning", "reason": "今のPython学習の中心になっているため"}},
    {{"title": "return", "status": "review", "reason": "以前少し曖昧だったため"}}
  ]
}}

科目:
{subject}

作成済み教科書:
{json.dumps(textbook_titles, ensure_ascii=False)}

理解度:
{json.dumps(understanding_summary, ensure_ascii=False)}
"""
        )
        data = parse_ai_json_object(response.output_text)
        items = data.get("items") if isinstance(data, dict) else None

        if not isinstance(items, list):
            return None

        normalized = []
        for item in items[:10]:
            title = truncate_text((item.get("title") or "").strip(), 80)
            if not title:
                continue

            normalized.append({
                "title": title,
                "status": normalize_roadmap_status(item.get("status")),
                "reason": truncate_text((item.get("reason") or "").strip(), 240)
            })

        return normalized or None
    except Exception:
        return None


def load_or_create_roadmap(db, user_id, subject, textbooks, understandings, thread_id=None):
    if is_roadmap_deleted(db, user_id, subject, thread_id):
        return []

    base_query = (
        db.query(StudyRoadmapItem)
        .filter(StudyRoadmapItem.user_id == user_id)
        .filter(StudyRoadmapItem.subject == subject)
    )
    query = base_query

    if thread_id is not None:
        query = query.filter(StudyRoadmapItem.thread_id == thread_id)

    existing_items = (
        query
        .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
        .all()
    )

    if not existing_items and thread_id is not None:
        unassigned_items = (
            base_query
            .filter(StudyRoadmapItem.thread_id.is_(None))
            .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
            .all()
        )

        for item in unassigned_items:
            item.thread_id = thread_id

        if unassigned_items:
            db.commit()
            existing_items = (
                query
                .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
                .all()
            )

    if not existing_items:
        roadmap_items = generate_roadmap_items_with_ai(subject, textbooks, understandings)
        source_type = "ai"

        if not roadmap_items:
            roadmap_items = fallback_roadmap_items(subject, textbooks, understandings)
            source_type = "fallback"

        for index, item in enumerate(roadmap_items):
            db.add(StudyRoadmapItem(
                user_id=user_id,
                thread_id=thread_id,
                subject=subject,
                title=item["title"],
                status=item["status"],
                reason=item["reason"],
                sort_order=index,
                source_type=source_type
            ))

        db.commit()
        existing_items = (
            query
            .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
            .all()
        )

    for item in existing_items:
        if item.source_type == "reset":
            continue

        inferred_status = infer_roadmap_status(item.title, textbooks, understandings)
        if inferred_status != "not_started" and item.status != inferred_status:
            item.status = inferred_status
            item.updated_at = app_now()

    db.commit()

    return [serialize_roadmap_item(item) for item in existing_items]


def reset_study_roadmap_for_thread(db, thread):
    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return

    subject = normalize_subject_title(thread.title) or thread.title
    roadmap_items = (
        db.query(StudyRoadmapItem)
        .filter(StudyRoadmapItem.user_id == thread.user_id)
        .filter(StudyRoadmapItem.subject == subject)
        .filter(or_(StudyRoadmapItem.thread_id == thread.id, StudyRoadmapItem.thread_id.is_(None)))
        .all()
    )

    for item in roadmap_items:
        item.status = "not_started"
        item.reason = "この会話が削除されたため、現在の学習計画を初期状態に戻しました。教科書・Memory・理解度は保持しています。"
        item.source_type = "reset"
        item.updated_at = app_now()

    db.query(StudyLessonState).filter(StudyLessonState.user_id == thread.user_id).filter(StudyLessonState.thread_id == thread.id).delete()


def build_roadmap_goal_summary(subject, roadmap_items):
    item_titles = [
        item.title
        for item in roadmap_items
        if item.title
    ]

    if not item_titles:
        return f"{subject}のロードマップ"

    return f"{subject}: " + " / ".join(item_titles[:6])


def deactivate_roadmap_goal_memories(db, user_id, subject, roadmap_items):
    clean_subject = normalize_subject_title(subject) or "学習相談"
    item_titles = [
        (item.title or "").strip()
        for item in roadmap_items
        if (item.title or "").strip()
    ]
    roadmap_terms = ["ロードマップ", "進捗", "現在地", "次のおすすめ", "学習順序", "未学習", "学習中"]
    goal_terms = ["学習目標", "目標", "マスター", "できるよう", "勉強したい", "学びたい", "進めたい"]

    candidate_memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .filter(Memory.is_active.is_(True))
        .filter(Memory.category.in_(["goal", "learning_goal", "roadmap_goal", "roadmap_progress", "roadmap_context"]))
        .all()
    )

    deactivated_count = 0

    for memory in candidate_memories:
        content = memory.content or ""
        category = memory.category or ""
        has_subject = clean_subject in content
        has_item_title = any(title and title in content for title in item_titles)
        has_roadmap_term = any(term in content for term in roadmap_terms)
        has_goal_term = any(term in content for term in goal_terms)

        should_deactivate = False

        if category.startswith("roadmap_"):
            should_deactivate = has_subject or has_item_title or has_roadmap_term or has_goal_term
        elif category == "learning_goal":
            should_deactivate = has_subject or has_item_title or has_roadmap_term or has_goal_term
        elif category == "goal":
            should_deactivate = (has_subject or has_item_title) and (has_roadmap_term or has_goal_term)

        if should_deactivate:
            memory.is_active = False
            deactivated_count += 1

    return deactivated_count


def detach_roadmap_from_thread(db, thread):
    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return

    subject = normalize_subject_title(thread.title) or thread.title

    (
        db.query(StudyRoadmapItem)
        .filter(StudyRoadmapItem.user_id == thread.user_id)
        .filter(StudyRoadmapItem.subject == subject)
        .filter(StudyRoadmapItem.thread_id == thread.id)
        .update({"thread_id": None}, synchronize_session=False)
    )
    (
        db.query(StudyLessonState)
        .filter(StudyLessonState.user_id == thread.user_id)
        .filter(StudyLessonState.thread_id == thread.id)
        .delete(synchronize_session=False)
    )


def has_active_roadmap_for_thread(thread):
    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return False

    subject = normalize_subject_title(thread.title) or thread.title
    db = SessionLocal()

    try:
        if is_roadmap_deleted(db, thread.user_id, subject, thread.id):
            return False

        roadmap_item = (
            db.query(StudyRoadmapItem)
            .filter(StudyRoadmapItem.user_id == thread.user_id)
            .filter(StudyRoadmapItem.subject == subject)
            .filter(or_(StudyRoadmapItem.thread_id == thread.id, StudyRoadmapItem.thread_id.is_(None)))
            .first()
        )

        return roadmap_item is not None
    finally:
        db.close()


def delete_study_roadmap(user_id, subject, thread_id=None):
    clean_subject = normalize_subject_title(subject) or "学習相談"
    db = SessionLocal()

    try:
        query = (
            db.query(StudyRoadmapItem)
            .filter(StudyRoadmapItem.user_id == user_id)
            .filter(StudyRoadmapItem.subject == clean_subject)
        )

        if thread_id is not None:
            query = query.filter(or_(StudyRoadmapItem.thread_id == thread_id, StudyRoadmapItem.thread_id.is_(None)))

        roadmap_items = query.all()
        deleted_goal = build_roadmap_goal_summary(clean_subject, roadmap_items)
        deactivated_memories = deactivate_roadmap_goal_memories(db, user_id, clean_subject, roadmap_items)
        deleted_items = len(roadmap_items)

        query.delete(synchronize_session=False)

        lesson_query = (
            db.query(StudyLessonState)
            .filter(StudyLessonState.user_id == user_id)
            .filter(StudyLessonState.subject == clean_subject)
        )

        if thread_id is not None:
            lesson_query = lesson_query.filter(StudyLessonState.thread_id == thread_id)

        lesson_query.delete(synchronize_session=False)

        (
            db.query(StudyUnderstanding)
            .filter(StudyUnderstanding.user_id == user_id)
            .filter(StudyUnderstanding.subject == clean_subject)
            .filter(StudyUnderstanding.scope_type == "roadmap")
            .delete(synchronize_session=False)
        )

        clear_roadmap_deletion_marker(db, user_id, clean_subject, thread_id)
        db.add(StudyRoadmapDeletion(
            user_id=user_id,
            thread_id=thread_id,
            subject=clean_subject,
            deleted_goal=deleted_goal
        ))
        db.commit()

        return {
            "deleted_items": deleted_items,
            "deactivated_memories": deactivated_memories
        }
    finally:
        db.close()


def load_bookshelf(subject, user_id):
    clean_subject = normalize_subject_title(subject) or "学習相談"
    db = SessionLocal()

    try:
        study_thread = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .filter(ChatThread.title == clean_subject)
            .order_by(ChatThread.updated_at.desc().nullslast(), ChatThread.created_at.desc())
            .first()
        )

        textbooks = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.user_id == user_id)
            .filter(StudyTextbook.subject == clean_subject)
            .order_by(StudyTextbook.updated_at.desc().nullslast(), StudyTextbook.created_at.desc())
            .all()
        )

        understandings = (
            db.query(StudyUnderstanding)
            .filter(StudyUnderstanding.user_id == user_id)
            .filter(StudyUnderstanding.subject == clean_subject)
            .order_by(StudyUnderstanding.updated_at.desc())
            .all()
        )

        return {
            "subject": clean_subject,
            "chat_url": f"/chat/{study_thread.id}" if study_thread else "",
            "roadmap": load_or_create_roadmap(
                db,
                user_id,
                clean_subject,
                textbooks,
                understandings,
                study_thread.id if study_thread else None
            ),
            "textbooks": [
                serialize_textbook_summary(textbook)
                for textbook in textbooks
            ]
        }
    finally:
        db.close()


def load_roadmap_overview(user_id):
    db = SessionLocal()

    try:
        subject_names = set()
        textbooks_by_subject = {}

        study_threads = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user_id)
            .filter(ChatThread.thread_type == STUDY_THREAD_TYPE)
            .order_by(ChatThread.updated_at.desc().nullslast(), ChatThread.created_at.desc())
            .all()
        )

        chat_urls = {}
        thread_ids = {}

        for thread in study_threads:
            subject = normalize_subject_title(thread.title) or "学習相談"
            subject_names.add(subject)
            chat_urls.setdefault(subject, f"/chat/{thread.id}")
            thread_ids.setdefault(subject, thread.id)

        textbooks = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.user_id == user_id)
            .order_by(StudyTextbook.updated_at.desc().nullslast(), StudyTextbook.created_at.desc())
            .all()
        )

        for textbook in textbooks:
            subject = normalize_subject_title(textbook.subject) or "学習相談"
            subject_names.add(subject)
            textbooks_by_subject.setdefault(subject, []).append(textbook)

        roadmaps = []

        for subject in sorted(subject_names):
            subject_textbooks = textbooks_by_subject.get(subject, [])
            understandings = (
                db.query(StudyUnderstanding)
                .filter(StudyUnderstanding.user_id == user_id)
                .filter(StudyUnderstanding.subject == subject)
                .order_by(StudyUnderstanding.updated_at.desc())
                .all()
            )
            roadmap_items = load_or_create_roadmap(
                db,
                user_id,
                subject,
                subject_textbooks,
                understandings,
                thread_ids.get(subject)
            )

            if not roadmap_items:
                continue

            subject_understanding = next(
                (
                    item
                    for item in understandings
                    if item.scope_type == "subject"
                ),
                None
            )
            current_item = next(
                (
                    item
                    for item in roadmap_items
                    if item["status"] in ["learning", "review"]
                ),
                None
            )
            next_item = next(
                (
                    item
                    for item in roadmap_items
                    if item["status"] == "not_started"
                ),
                None
            )

            roadmaps.append({
                "subject": subject,
                "thread_id": thread_ids.get(subject),
                "chat_url": chat_urls.get(subject, ""),
                "bookshelf_url": f"/bookshelf/{quote(subject)}",
                "understanding_percent": subject_understanding.percent if subject_understanding else 0,
                "current_item": current_item,
                "next_item": next_item,
                "textbooks": [
                    serialize_textbook_summary(textbook)
                    for textbook in subject_textbooks
                ],
                "items": roadmap_items
            })

        return roadmaps
    finally:
        db.close()


def format_roadmap_items_for_prompt(roadmap_items):
    if not roadmap_items:
        return "ロードマップはまだありません。必要ならこの科目の基礎から作って進めてください。"

    lines = []

    for index, item in enumerate(roadmap_items[:12], start=1):
        lines.append(
            f"{index}. [{get_roadmap_status_label(item.status)}] {item.title}"
            f" - {item.reason or '理由は未登録'}"
        )

    current_item = choose_roadmap_focus_item(roadmap_items)
    skipped_items = [
        item.title
        for item in roadmap_items
        if normalize_roadmap_status(item.status) == "skipped"
    ]

    text_value = "\n".join(lines)
    text_value += f"\n現在地: {current_item.title if current_item else '未設定'}"
    text_value += f"\n飛ばした単元: {', '.join(skipped_items) if skipped_items else 'なし'}"

    return text_value


def format_textbooks_for_prompt(textbooks):
    if not textbooks:
        return "この科目の教科書はまだありません。授業内容から必要に応じて作成できます。"

    lines = []

    for textbook in textbooks[:5]:
        lines.append(
            f"- {textbook.title or '無題の教科書'}"
            f" / 重要ポイント: {truncate_text(textbook.key_points or textbook.personal_points or '', 120)}"
        )

    return "\n".join(lines)


def format_understandings_for_prompt(understandings):
    if not understandings:
        return "理解度データはまだありません。会話と回答から少しずつ推定してください。"

    lines = []

    for item in understandings[:12]:
        label = item.item_name or item.scope_type or "項目"
        lines.append(
            f"- {label}: {normalize_percent(item.percent)}%"
            f" / 前回差分 {item.delta_percent or 0}%"
            f" / 根拠: {truncate_text(item.evidence or '', 100)}"
        )

    return "\n".join(lines)


def normalize_lesson_level(level):
    return level if level in LESSON_LEVEL_ORDER else "term"


def move_lesson_level(level, step):
    current_level = normalize_lesson_level(level)
    index = LESSON_LEVEL_ORDER.index(current_level)
    next_index = max(0, min(len(LESSON_LEVEL_ORDER) - 1, index + step))
    return LESSON_LEVEL_ORDER[next_index]


def clamp_percent(value, default=35):
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = default

    return max(0, min(100, percent))


def parse_recent_problem_history(text_value):
    try:
        data = json.loads(text_value or "[]")
    except json.JSONDecodeError:
        data = []

    if not isinstance(data, list):
        return []

    return [
        truncate_text(str(item), 140)
        for item in data
        if str(item).strip()
    ][-8:]


def load_or_create_lesson_state(db, user_id, thread_id, subject):
    state = (
        db.query(StudyLessonState)
        .filter(StudyLessonState.user_id == user_id)
        .filter(StudyLessonState.thread_id == thread_id)
        .first()
    )

    if state is not None:
        return state

    state = StudyLessonState(
        user_id=user_id,
        thread_id=thread_id,
        subject=subject,
        live_understanding=35,
        question_level="term",
        current_focus="最初のつまずきを確認する"
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def apply_lesson_message_signal(db, state, message):
    message = (message or "").strip()

    if state is None or not message:
        return "授業中の理解判断: 新しい発言による変更なし"

    understanding = clamp_percent(state.live_understanding, 35)
    level = normalize_lesson_level(state.question_level)
    signal = "授業中の理解判断: 新しい発言による変更なし"

    if should_make_study_weak_note(message):
        understanding = max(10, understanding - 14)
        level = move_lesson_level(level, -1)
        state.weak_points = truncate_text(
            "\n".join(filter(None, [state.weak_points, f"直近のつまずき: {message}"])),
            900
        )
        signal = "授業中の理解判断: ユーザーが分からないと言っているため、基礎へ少し戻す"
    elif contains_any_word(message, LESSON_UNDERSTOOD_WORDS):
        understanding = min(88, understanding + 12)
        if understanding >= 65:
            level = move_lesson_level(level, 1)
        state.mastered_points = truncate_text(
            "\n".join(filter(None, [state.mastered_points, f"理解できた反応: {message}"])),
            900
        )
        signal = "授業中の理解判断: 理解できた反応があるため、次の難易度へ進める"
    elif "応用問題" in message:
        understanding = max(understanding, 58)
        level = move_lesson_level(level, 1)
        signal = "授業中の理解判断: 応用問題を希望しているため、少し実践寄りにする"
    elif "理解確認" in message:
        level = "short_answer"
        signal = "授業中の理解判断: 理解確認を希望しているため、短い確認問題にする"

    state.live_understanding = understanding
    state.question_level = level
    state.last_signal = signal
    state.updated_at = app_now()
    db.commit()
    return signal


def infer_problem_level_from_text(text_value):
    text_value = text_value or ""

    if "ミニアプリ" in text_value or "小さなアプリ" in text_value:
        return "mini_app"
    if "コードを書" in text_value or "実装" in text_value:
        return "code_creation"
    if "修正" in text_value or "直して" in text_value:
        return "code_fix"
    if "コード" in text_value or "読解" in text_value:
        return "code_reading"
    if "記述" in text_value or "理由" in text_value or "説明して" in text_value:
        return "short_answer"
    return "term"


def extract_problem_prompt_summary(text_value):
    lines = [line.strip() for line in (text_value or "").splitlines() if line.strip()]
    candidates = []
    markers = ["問題", "理解確認", "応用", "やってみよう", "考えてみて", "コード"]

    for line in lines:
        if any(marker in line for marker in markers):
            candidates.append(line)

    if not candidates:
        return ""

    return truncate_text(" / ".join(candidates[:3]), 220)


def record_lesson_problem_history(thread, user_id, teacher_message):
    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return

    problem_summary = extract_problem_prompt_summary(teacher_message)

    if not problem_summary:
        return

    subject = normalize_subject_title(thread.title) or "学習相談"
    db = SessionLocal()

    try:
        state = load_or_create_lesson_state(db, user_id, thread.id, subject)
        history = parse_recent_problem_history(state.recent_problem_history)
        history.append(problem_summary)
        state.recent_problem_history = json.dumps(history[-8:], ensure_ascii=False)
        state.question_level = infer_problem_level_from_text(teacher_message)
        state.current_focus = truncate_text(problem_summary, 120)
        state.updated_at = app_now()
        db.commit()
    finally:
        db.close()


def format_lesson_state_for_prompt(state):
    if state is None:
        return "授業中の一時判断はまだありません。最初は小さく理解確認してください。"

    history = parse_recent_problem_history(state.recent_problem_history)
    level = normalize_lesson_level(state.question_level)

    return f"""
授業中の一時判断（教科書理解度とは別）:
- 現在の理解感: {clamp_percent(state.live_understanding, 35)}%
- 今の問題レベル: {LESSON_LEVEL_LABELS.get(level, "用語確認")}
- 現在の焦点: {state.current_focus or "未設定"}
- 授業中に理解できたこと: {state.mastered_points or "まだ少ない"}
- 授業中のつまずき: {state.weak_points or "まだ少ない"}
- 最近出した問題: {", ".join(history) if history else "まだありません"}
- 直近判断: {state.last_signal or "なし"}

授業進行ルール:
- 上の最近出した問題と同じ問題・似すぎた問題を繰り返さないでください。
- 復習が必要な場合でも、問題文・状況・出題方法を変えてください。
- 理解感が高い場合は、用語確認を続けず、記述→コード読解→コード修正→コード作成→ミニアプリ制作へ少しずつ進めてください。
- 理解感が低い場合は、基礎へ戻し、説明を短く分けてください。
- 毎回最初から説明し直さず、理解済みの内容は短く確認して次へ進んでください。
"""


def build_study_context_for_prompt(thread, user_id, latest_message=""):
    subject = normalize_subject_title(thread.title) or "学習相談"
    db = SessionLocal()

    try:
        textbooks = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.user_id == user_id)
            .filter(StudyTextbook.subject == subject)
            .order_by(StudyTextbook.updated_at.desc().nullslast(), StudyTextbook.created_at.desc())
            .all()
        )
        understandings = (
            db.query(StudyUnderstanding)
            .filter(StudyUnderstanding.user_id == user_id)
            .filter(StudyUnderstanding.subject == subject)
            .order_by(StudyUnderstanding.updated_at.desc())
            .all()
        )

        roadmap_deleted = is_roadmap_deleted(db, user_id, subject, thread.id)
        roadmap_intent = {"type": "", "item_title": ""}
        roadmap_recreated = False

        if roadmap_deleted and is_roadmap_create_message(latest_message):
            clear_roadmap_deletion_marker(db, user_id, subject, thread.id)
            roadmap_deleted = False
            roadmap_recreated = True

        if roadmap_deleted:
            roadmap_items = []
        else:
            load_or_create_roadmap(db, user_id, subject, textbooks, understandings, thread.id)
            roadmap_items = (
                db.query(StudyRoadmapItem)
                .filter(StudyRoadmapItem.user_id == user_id)
                .filter(StudyRoadmapItem.subject == subject)
                .filter(StudyRoadmapItem.thread_id == thread.id)
                .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
                .all()
            )
            roadmap_intent = apply_roadmap_message_intent(db, roadmap_items, latest_message)
            roadmap_items = (
                db.query(StudyRoadmapItem)
                .filter(StudyRoadmapItem.user_id == user_id)
                .filter(StudyRoadmapItem.subject == subject)
                .filter(StudyRoadmapItem.thread_id == thread.id)
                .order_by(StudyRoadmapItem.sort_order.asc(), StudyRoadmapItem.id.asc())
                .all()
            )
        lesson_state = load_or_create_lesson_state(db, user_id, thread.id, subject)
        lesson_signal = apply_lesson_message_signal(db, lesson_state, latest_message)
        lesson_state = load_or_create_lesson_state(db, user_id, thread.id, subject)

        intent_text = "今回のロードマップ指示: なし"

        if roadmap_intent["type"] == "follow":
            intent_text = (
                "今回のロードマップ指示: ユーザーはロードマップ通りに進むと言っています。"
                f"現在地「{roadmap_intent['item_title']}」から授業を始めてください。"
            )
        elif roadmap_intent["type"] == "skip":
            intent_text = (
                "今回のロードマップ指示: ユーザーは"
                f"「{roadmap_intent['item_title']}」を飛ばすと言っています。"
                "今後は飛ばした単元として扱い、必要な前提だけ短く補足してください。"
            )
        elif roadmap_recreated:
            intent_text = (
                "今回のロードマップ指示: ユーザーは削除後の新しいロードマップ作成を求めています。"
                "過去に削除した目標や現在地を引き継がず、残っている教科書・理解度だけ参考にしてゼロから授業を始めてください。"
            )

        roadmap_prompt = format_roadmap_items_for_prompt(roadmap_items)

        if roadmap_deleted:
            roadmap_prompt = (
                "この会話のロードマップはユーザーが削除済みです。"
                "過去のロードマップの目標・現在地・進捗・次のおすすめ・スキップ単元は参照しないでください。"
                "ユーザーが新しい目標を話した場合だけ、新しいロードマップを作成できることを提案してください。"
            )

        return f"""
学習基本情報:
{format_study_context_for_prompt(thread)}

ロードマップ:
{roadmap_prompt}

{intent_text}

教科書:
{format_textbooks_for_prompt(textbooks)}

理解度:
{format_understandings_for_prompt(understandings)}

授業中の進行状態:
{format_lesson_state_for_prompt(lesson_state)}
{lesson_signal}

ロードマップ利用ルール:
- 返答前に、必ず上のロードマップ・現在地・飛ばした単元・理解度を確認してください。
- 「ロードマップ通りに進もう」と言われたら、現在地または次の未学習単元から授業を始めてください。
- 「ここは飛ばす」と言われたら、その単元を飛ばした前提で進め、必要な前提知識だけ短く補ってください。
- 順番は強制せず、ユーザーが選んだ単元を尊重してください。
"""
    finally:
        db.close()


def load_textbook_options_for_subject(subject, user_id):
    clean_subject = normalize_subject_title(subject)

    if not clean_subject:
        return []

    db = SessionLocal()

    try:
        textbooks = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.user_id == user_id)
            .filter(StudyTextbook.subject == clean_subject)
            .order_by(StudyTextbook.updated_at.desc().nullslast(), StudyTextbook.created_at.desc())
            .limit(8)
            .all()
        )

        return [
            {
                "id": textbook.id,
                "title": textbook.title,
                "updated_at": format_date(textbook.updated_at)
            }
            for textbook in textbooks
        ]
    finally:
        db.close()


def format_textbook_source_material(thread_id, user_id):
    chat_items = load_chat_items(thread_id, user_id)
    recent_items = chat_items[-16:]

    if not recent_items:
        return "まだ授業内容はありません。"

    source_text = ""

    for item in recent_items:
        role_label = "ユーザー" if item["role"] == "user" else "先生"
        source_text += f"{role_label}: {item['content']}\n"

    return source_text


def fallback_textbook_preview(thread, user_id, source_material):
    existing_textbooks = load_textbook_options_for_subject(thread.title, user_id)
    first_existing = existing_textbooks[0] if existing_textbooks else None
    action_mode = "update" if first_existing else "create"

    return {
        "mode": action_mode,
        "target_textbook_id": first_existing["id"] if first_existing else None,
        "target_textbook_title": first_existing["title"] if first_existing else "",
        "title": f"{thread.title}の授業まとめ",
        "bookshelf_subject": thread.title,
        "introduction": f"今日は{thread.title}で扱った内容を、あとから読み返せる一章として整理します。この章を読むと、授業で出てきた考え方をもう一度たどれるようになります。",
        "learning_image": "まずは、授業内容を机の上に並べた道具だと考えてみましょう。何に使う道具なのか、どの順番で使うのかを確認すると、全体像が見えやすくなります。",
        "beginner_explanation": "専門用語だけで覚えるのではなく、何のために使うのかを先に確認します。細かい言葉は、使い道が分かってから覚えると理解しやすくなります。",
        "visual_diagram": "授業内容\n  ↓\n大事な考え方\n  ↓\n例で確認\n  ↓\n自分で説明してみる",
        "code_example": source_material[:900],
        "code_walkthrough": "授業で出てきた例を、上から順番に確認します。どの行が何をしているのかを、次回の授業で一緒に深掘りできます。",
        "basic_explanation": "",
        "concrete_examples": "",
        "key_points": "1. まず全体像をつかむ\n2. 言葉の意味より先に使い道を見る\n3. 自分の言葉で説明できるか確認する",
        "personal_points": "あなたが会話の中で分かりにくそうだった部分を、次回の授業で重点的に確認します。",
        "weak_points": "会話の中で分かりにくそうだった内容を確認します。",
        "unclear_points": "まだ曖昧な内容は、次回の授業で先生に質問できます。",
        "common_mistakes": "似た言葉や処理の違いを混同しないように注意します。",
        "check_questions": "1. 今日扱った内容を自分の言葉で説明してください。",
        "application_questions": "1. 今日の内容を使って、短い例を1つ作ってください。",
        "model_answers": "自分の回答と授業内容を照らし合わせて確認してください。",
        "detailed_explanations": "分からない部分は、教科書詳細の「先生に質問する」から授業へ戻れます。",
        "related_textbooks": "",
        "update_summary": "直近の授業内容を教科書に追加します。"
    }


def normalize_textbook_preview(raw_data, thread, user_id):
    data = raw_data if isinstance(raw_data, dict) else {}
    subject = normalize_subject_title(data.get("bookshelf_subject") or thread.title) or thread.title
    existing_ids = {
        item["id"]: item["title"]
        for item in load_textbook_options_for_subject(subject, user_id)
    }
    mode = data.get("mode") if data.get("mode") in ["create", "update"] else "create"
    target_textbook_id = data.get("target_textbook_id")

    try:
        target_textbook_id = int(target_textbook_id) if target_textbook_id else None
    except (TypeError, ValueError):
        target_textbook_id = None

    if mode == "update" and target_textbook_id not in existing_ids:
        mode = "create"
        target_textbook_id = None

    title = truncate_text(data.get("title") or f"{subject}の授業まとめ", 120)

    preview = {
        "mode": mode,
        "target_textbook_id": target_textbook_id,
        "target_textbook_title": existing_ids.get(target_textbook_id, ""),
        "title": title,
        "bookshelf_subject": subject,
        "update_summary": (data.get("update_summary") or "授業内容を教科書に反映します。").strip()
    }

    for field_name in TEXTBOOK_CONTENT_FIELDS:
        value = data.get(field_name)
        if isinstance(value, list):
            value = "\n".join([str(item).strip() for item in value if str(item).strip()])
        preview[field_name] = (value or "").strip()

    return preview


def create_textbook_preview(thread, user_id, source_note=""):
    source_material = format_textbook_source_material(thread.id, user_id)
    memories = load_memories(user_id)
    existing_textbooks = load_textbook_options_for_subject(thread.title, user_id)

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=f"""
あなたはStudy PASの「教科書を編集する先生」です。
直近の授業内容から、ユーザー専用の一章を執筆してください。

最重要方針:
- 情報を項目ごとに整理したAIメモを作らない。
- 参考書や教科書のように、自然に読み進められる流れで書く。
- 読者は初心者。専門用語を急に並べず、身近なイメージから入る。
- 「先生が教材を書いている」文章にする。
- 情報量より、読む順番と理解の流れを優先する。

重要なルール:
- ユーザーが承認する前なので、保存した前提で書かない。
- 後から見返した時に分かりやすいタイトルを自動生成する。
- 既存教科書に近い内容がある場合は mode を "update" にし、target_textbook_id に既存教科書のidを入れる。
- 近い教科書がなければ mode を "create" にする。
- 取得できない情報は無理に作らず、会話とMemoryから分かる範囲で書く。
- introduction は「今日は〇〇について学びます」「この章を読むと何ができるか」から始める。
- learning_image は料理・道具・学校・本など、身近なたとえで説明する。
- beginner_explanation は専門用語をなるべく避け、初心者に向けて説明する。
- visual_diagram は文章だけでなく、簡単なテキスト図やフローチャートを書く。
- code_example はプログラミングなら実際のコードを書く。プログラミング以外なら、式・例文・問題例を書く。
- code_walkthrough はコードや例を一行ずつ、なぜ必要かまで説明する。
- key_points は最後に「ここだけは覚えよう」を3〜5個まとめる。
- personal_points で初めてMemoryを使い、本人専用の注意点や説明方針を書く。
- 理解確認問題は5問、応用問題は10問を作る。
- 模範解答と詳しい解説は、答えだけでなく考え方まで説明する。
- 必ずJSONだけで返す。

返答形式:
{{
  "mode": "create",
  "target_textbook_id": null,
  "title": "Pythonの戻り値（return）の基本と使い方",
  "bookshelf_subject": "{thread.title}",
  "introduction": "",
  "learning_image": "",
  "beginner_explanation": "",
  "visual_diagram": "",
  "code_example": "",
  "code_walkthrough": "",
  "basic_explanation": "",
  "concrete_examples": "",
  "key_points": "",
  "personal_points": "",
  "weak_points": "",
  "unclear_points": "",
  "common_mistakes": "",
  "check_questions": "",
  "application_questions": "",
  "model_answers": "",
  "detailed_explanations": "",
  "related_textbooks": "",
  "update_summary": ""
}}

科目:
{thread.title}

既存教科書:
{json.dumps(existing_textbooks, ensure_ascii=False)}

共有Memory:
{memories}

ユーザー補足:
{source_note}

直近の授業:
{source_material}
"""
        )
        preview_data = parse_ai_json_object(response.output_text)
        return normalize_textbook_preview(preview_data, thread, user_id)
    except Exception:
        return fallback_textbook_preview(thread, user_id, source_material)


def append_textbook_section(current_text, added_text):
    current_text = (current_text or "").strip()
    added_text = (added_text or "").strip()

    if not added_text:
        return current_text

    if not current_text:
        return added_text

    date_label = app_now().strftime("%Y-%m-%d")
    return f"{current_text}\n\n---\n\n{date_label} 追記\n{added_text}"


def confirm_textbook_preview(payload, user_id):
    thread = load_chat_thread(payload.thread_id, user_id)

    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return None

    title = truncate_text(payload.title or f"{thread.title}の授業まとめ", 180)
    subject = normalize_subject_title(payload.bookshelf_subject or thread.title) or thread.title
    mode = payload.mode if payload.mode in ["create", "update"] else "create"
    update_summary = (payload.update_summary or "授業内容を教科書に反映しました。").strip()

    db = SessionLocal()

    try:
        textbook = None

        if mode == "update" and payload.target_textbook_id:
            textbook = (
                db.query(StudyTextbook)
                .filter(StudyTextbook.id == payload.target_textbook_id)
                .filter(StudyTextbook.user_id == user_id)
                .first()
            )

        if textbook:
            textbook.title = textbook.title or title
            textbook.subject = textbook.subject or subject
            textbook.thread_id = textbook.thread_id or thread.id

            for field_name in TEXTBOOK_CONTENT_FIELDS:
                current_value = getattr(textbook, field_name)
                added_value = getattr(payload, field_name)
                setattr(textbook, field_name, append_textbook_section(current_value, added_value))

            textbook.updated_at = app_now()
            action_type = "updated"
        else:
            textbook = StudyTextbook(
                user_id=user_id,
                thread_id=thread.id,
                subject=subject,
                title=title,
                introduction=payload.introduction,
                learning_image=payload.learning_image,
                beginner_explanation=payload.beginner_explanation,
                visual_diagram=payload.visual_diagram,
                code_example=payload.code_example,
                code_walkthrough=payload.code_walkthrough,
                personal_points=payload.personal_points,
                basic_explanation=payload.basic_explanation,
                concrete_examples=payload.concrete_examples,
                key_points=payload.key_points,
                weak_points=payload.weak_points,
                unclear_points=payload.unclear_points,
                common_mistakes=payload.common_mistakes,
                check_questions=payload.check_questions,
                application_questions=payload.application_questions,
                model_answers=payload.model_answers,
                detailed_explanations=payload.detailed_explanations,
                related_textbooks=payload.related_textbooks
            )
            db.add(textbook)
            db.flush()
            action_type = "created"

        history = StudyTextbookUpdate(
            user_id=user_id,
            textbook_id=textbook.id,
            action_type=action_type,
            summary=update_summary if action_type == "updated" else "教科書を作成"
        )
        db.add(history)
        db.commit()
        db.refresh(textbook)

        updates = (
            db.query(StudyTextbookUpdate)
            .filter(StudyTextbookUpdate.user_id == user_id)
            .filter(StudyTextbookUpdate.textbook_id == textbook.id)
            .order_by(StudyTextbookUpdate.created_at.desc())
            .all()
        )

        return serialize_textbook_detail(textbook, updates)
    finally:
        db.close()


def normalize_percent(value):
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        percent = 0

    return max(0, min(100, percent))


def calculate_understanding_percent(previous_percent, ai_score, assessment_count):
    previous_percent = normalize_percent(previous_percent)
    ai_score = normalize_percent(ai_score)

    if assessment_count <= 0:
        cap = 78
    elif assessment_count < 3:
        cap = 88
    elif assessment_count < 5:
        cap = 95
    elif previous_percent >= 95 and ai_score >= 95:
        cap = 100
    else:
        cap = 97

    capped_score = min(ai_score, cap)

    if previous_percent <= 0:
        return capped_score

    if capped_score >= previous_percent:
        return normalize_percent(previous_percent * 0.55 + capped_score * 0.45)

    return normalize_percent(previous_percent * 0.72 + capped_score * 0.28)


def calculate_next_review_plan(percent, previous_interval_days, review_count, answer_type, used_hint, weak_points, unclear_points):
    percent = normalize_percent(percent)
    previous_interval_days = max(1, int(previous_interval_days or 1))
    review_count = int(review_count or 0)
    has_weak_signal = bool((weak_points or "").strip() or (unclear_points or "").strip() or used_hint)

    if percent < 50:
        interval_days = 1
    elif percent < 70:
        interval_days = 2
    elif percent < 85:
        interval_days = 4
    elif percent < 95:
        interval_days = max(7, previous_interval_days + 2)
    else:
        if answer_type == "review":
            interval_days = max(14, previous_interval_days * 2)
        else:
            interval_days = max(10, previous_interval_days)

    if has_weak_signal:
        interval_days = max(1, int(round(interval_days * 0.65)))

    if percent >= 100 and review_count >= 3:
        retention_level = "mastered"
        interval_days = max(interval_days, 90)
    elif percent >= 90 and review_count >= 2:
        retention_level = "stable"
    elif percent >= 60:
        retention_level = "reviewing"
    else:
        retention_level = "new"

    return {
        "interval_days": min(interval_days, 365),
        "next_review_at": app_now() + timedelta(days=min(interval_days, 365)),
        "retention_level": retention_level
    }


def fallback_assessment_result(answer_text):
    return {
        "score_percent": 45,
        "feedback": "回答は受け取りました。AI添削に失敗したため、もう一度送ると詳しく確認できます。",
        "understood_points": "回答しようとしている点は学習の材料になります。",
        "weak_points": "どこが分かっているか、どこが曖昧かをもう少し分けて確認する必要があります。",
        "unclear_points": "回答内容からは、理解できている範囲を十分に判断できませんでした。",
        "thinking_gap": "考え方のずれは未判定です。",
        "next_review_content": "教科書の基本説明と重要ポイントを読み直してから、もう一度回答してみてください。",
        "item_scores": []
    }


def parse_ai_json_object(text_value):
    clean_text = (text_value or "").strip()

    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
        clean_text = re.sub(r"\s*```$", "", clean_text)

    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError:
        start = clean_text.find("{")
        end = clean_text.rfind("}")

        if start < 0 or end < start:
            return None

        try:
            data = json.loads(clean_text[start:end + 1])
        except json.JSONDecodeError:
            return None

    return data if isinstance(data, dict) else None


def assess_textbook_answer(textbook, answer_type, answer_text, used_hint, previous_summary):
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=f"""
あなたはStudy PASの先生です。
ユーザーが教科書の問題に回答しました。
単なる正誤ではなく、考え方・理解度・ズレ・次に復習すべき内容を分析してください。

重要:
- 正答率だけで判断しない。
- 1回の回答で100%と判断しない。
- ヒントを使った場合は、理解度を少し慎重に見る。
- 同じミスがありそうなら指摘する。
- item_scores には、この教科書内の重要項目を3〜6個ほど入れる。
- 必ずJSONだけで返す。

返答形式:
{{
  "score_percent": 72,
  "feedback": "全体の添削コメント",
  "understood_points": "理解できている点",
  "weak_points": "苦手・間違えた点",
  "unclear_points": "まだ曖昧な点",
  "thinking_gap": "考え方がずれている点",
  "next_review_content": "次に復習すべき内容",
  "item_scores": [
    {{"item_name": "return", "score_percent": 68, "reason": "戻り値の使い方がまだ曖昧"}}
  ]
}}

回答タイプ:
{answer_type}

ヒント使用:
{used_hint}

前回までの理解度:
{previous_summary}

教科:
{textbook.subject}

教科書タイトル:
{textbook.title}

教科書内容:
導入:
{textbook.introduction}

イメージ:
{textbook.learning_image}

基本説明:
{textbook.beginner_explanation or textbook.basic_explanation}

図・流れ:
{textbook.visual_diagram}

実際のコード・実例:
{textbook.code_example}

コード解説・流れ:
{textbook.code_walkthrough}

重要ポイント:
{textbook.key_points}

あなた専用ポイント:
{textbook.personal_points}

理解確認問題:
{textbook.check_questions}

応用問題:
{textbook.application_questions}

模範解答:
{textbook.model_answers}

詳しい解説:
{textbook.detailed_explanations}

ユーザー回答:
{answer_text}
"""
        )

        data = parse_ai_json_object(response.output_text)

        if data is None:
            return fallback_assessment_result(answer_text)

        return data
    except Exception:
        return fallback_assessment_result(answer_text)


def get_understanding_summary(db, user_id, textbook):
    understandings = (
        db.query(StudyUnderstanding)
        .filter(StudyUnderstanding.user_id == user_id)
        .filter(StudyUnderstanding.subject == textbook.subject)
        .filter(
            or_(
                StudyUnderstanding.textbook_id == textbook.id,
                StudyUnderstanding.scope_type == "subject"
            )
        )
        .order_by(StudyUnderstanding.updated_at.desc())
        .all()
    )

    if not understandings:
        return "まだ理解度は記録されていません。"

    summary = ""

    for item in understandings[:8]:
        summary += f"{item.scope_type}:{item.item_name} {item.percent or 0}% / "

    return summary


def get_or_create_understanding(db, user_id, subject, textbook_id, scope_type, item_name):
    understanding = (
        db.query(StudyUnderstanding)
        .filter(StudyUnderstanding.user_id == user_id)
        .filter(StudyUnderstanding.subject == subject)
        .filter(StudyUnderstanding.scope_type == scope_type)
        .filter(StudyUnderstanding.item_name == item_name)
        .filter(StudyUnderstanding.textbook_id == textbook_id)
        .first()
    )

    if understanding:
        return understanding

    understanding = StudyUnderstanding(
        user_id=user_id,
        subject=subject,
        textbook_id=textbook_id,
        scope_type=scope_type,
        item_name=item_name,
        percent=0,
        previous_percent=0,
        delta_percent=0
    )
    db.add(understanding)
    db.flush()
    return understanding


def update_understanding(db, understanding, ai_score, assessment_count, evidence, review_context=None):
    previous_percent = normalize_percent(understanding.percent)
    next_percent = calculate_understanding_percent(previous_percent, ai_score, assessment_count)

    understanding.previous_percent = previous_percent
    understanding.percent = next_percent
    understanding.delta_percent = next_percent - previous_percent
    understanding.evidence = evidence
    understanding.last_assessed_at = app_now()
    understanding.updated_at = app_now()

    if review_context:
        if review_context.get("answer_type") == "review":
            understanding.review_count = (understanding.review_count or 0) + 1

        review_plan = calculate_next_review_plan(
            percent=next_percent,
            previous_interval_days=understanding.review_interval_days or 1,
            review_count=understanding.review_count or 0,
            answer_type=review_context.get("answer_type"),
            used_hint=review_context.get("used_hint"),
            weak_points=review_context.get("weak_points"),
            unclear_points=review_context.get("unclear_points")
        )
        understanding.next_review_at = review_plan["next_review_at"]
        understanding.review_interval_days = review_plan["interval_days"]
        understanding.retention_level = review_plan["retention_level"]

    return understanding


def submit_textbook_answer(textbook_id, user_id, payload):
    answer_text = (payload.answer_text or "").strip()

    if not answer_text:
        return None

    answer_type = payload.answer_type if payload.answer_type in ["check", "application", "review"] else "check"
    db = SessionLocal()

    try:
        textbook = (
            db.query(StudyTextbook)
            .filter(StudyTextbook.id == textbook_id)
            .filter(StudyTextbook.user_id == user_id)
            .first()
        )

        if textbook is None:
            return None

        assessment_count = (
            db.query(StudyAssessment)
            .filter(StudyAssessment.user_id == user_id)
            .filter(StudyAssessment.textbook_id == textbook.id)
            .count()
        )
        previous_summary = get_understanding_summary(db, user_id, textbook)
        result = assess_textbook_answer(
            textbook=textbook,
            answer_type=answer_type,
            answer_text=answer_text,
            used_hint=payload.used_hint,
            previous_summary=previous_summary
        )
        score_percent = normalize_percent(result.get("score_percent"))

        assessment = StudyAssessment(
            user_id=user_id,
            textbook_id=textbook.id,
            subject=textbook.subject,
            answer_type=answer_type,
            answer_text=answer_text,
            feedback=(result.get("feedback") or "").strip(),
            score_percent=score_percent,
            understood_points=(result.get("understood_points") or "").strip(),
            weak_points=(result.get("weak_points") or "").strip(),
            unclear_points=(result.get("unclear_points") or "").strip(),
            thinking_gap=(result.get("thinking_gap") or "").strip(),
            next_review_content=(result.get("next_review_content") or "").strip(),
            used_hint=bool(payload.used_hint)
        )
        db.add(assessment)
        db.flush()

        review_context = {
            "answer_type": answer_type,
            "used_hint": bool(payload.used_hint),
            "weak_points": assessment.weak_points,
            "unclear_points": assessment.unclear_points
        }

        textbook_understanding = get_or_create_understanding(
            db,
            user_id=user_id,
            subject=textbook.subject,
            textbook_id=textbook.id,
            scope_type="textbook",
            item_name=textbook.title
        )
        update_understanding(
            db,
            textbook_understanding,
            score_percent,
            assessment_count,
            assessment.feedback,
            review_context
        )
        assessment.next_review_at = textbook_understanding.next_review_at
        assessment.review_interval_days = textbook_understanding.review_interval_days

        subject_understanding = get_or_create_understanding(
            db,
            user_id=user_id,
            subject=textbook.subject,
            textbook_id=None,
            scope_type="subject",
            item_name=textbook.subject
        )
        current_subject_percent = normalize_percent(subject_understanding.percent)
        subject_score = (
            score_percent
            if current_subject_percent <= 0
            else normalize_percent((current_subject_percent + score_percent) / 2)
        )
        update_understanding(
            db,
            subject_understanding,
            subject_score,
            assessment_count,
            f"{textbook.title}の回答結果を反映",
            review_context
        )

        item_scores = result.get("item_scores") if isinstance(result.get("item_scores"), list) else []

        for item in item_scores[:8]:
            item_name = truncate_text((item.get("item_name") or "").strip(), 120)
            if not item_name:
                continue

            item_understanding = get_or_create_understanding(
                db,
                user_id=user_id,
                subject=textbook.subject,
                textbook_id=textbook.id,
                scope_type="item",
                item_name=item_name
            )
            update_understanding(
                db,
                item_understanding,
                normalize_percent(item.get("score_percent")),
                assessment_count,
                (item.get("reason") or assessment.feedback or "").strip(),
                review_context
            )

        textbook.updated_at = app_now()
        db.commit()
        db.refresh(assessment)

        if assessment.weak_points:
            save_or_update_memory(
                content=f"{textbook.subject}の苦手: {assessment.weak_points}",
                category="weak_area",
                importance=5,
                confidence=0.86,
                source_type="ai_inference",
                status="confirmed",
                user_id=user_id
            )

        if assessment.unclear_points:
            save_or_update_memory(
                content=f"{textbook.subject}でまだ曖昧な内容: {assessment.unclear_points}",
                category="weak_area",
                importance=4,
                confidence=0.8,
                source_type="ai_inference",
                status="confirmed",
                user_id=user_id
            )

        textbook_detail = load_textbook(textbook.id, user_id)

        return {
            "assessment": serialize_assessment(assessment),
            "textbook": textbook_detail
        }
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


def delete_chat_thread(thread_id, user_id, delete_roadmap=False):
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

        if delete_roadmap and thread.thread_type == STUDY_THREAD_TYPE:
            delete_study_roadmap(user_id, thread.title, thread.id)
        else:
            detach_roadmap_from_thread(db, thread)

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


def extract_study_learning_notes(subject, user_message, teacher_message, history, lesson_end=False):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
あなたはStudy PASの授業記録を作るAIです。
この1ターンの会話から、次回の授業に役立つ「苦手ノート」「学習レポート」「次回の一歩」だけを短く整理してください。

目的:
- ユーザーが「わからない」「むずい」「曖昧」と言った時に、何が分からなかったのかを会話項目ごとに残す
- 「今日はここまで」「今日のまとめ」の時に、次回に引き継げる短い学習レポートを残す
- ただし、推測しすぎず、会話から読み取れる範囲だけにする

必ずJSONだけで返してください。

返答形式:
{{
  "should_save_weak_note": true,
  "weak_note": "Pythonのreturnが何を返す仕組みなのかが曖昧。",
  "should_save_lesson_report": true,
  "lesson_report": "今日はPythonのreturnの意味を確認した。次回はprintとの違いを短いコードで練習する。",
  "next_step": "returnを使う短い関数を1つ書いて、戻り値を確認する。"
}}

保存しない場合は false と空文字にしてください。
weak_note は、ユーザーが本当に困っている内容がある時だけ true にしてください。
lesson_report は、lesson_end が true の時、または会話が一区切りになっている時だけ true にしてください。
next_step は、次回の授業で最初にやる小さな行動を1文にしてください。

科目:
{subject}

lesson_end:
{lesson_end}

直近履歴:
{history}

ユーザー発言:
{user_message}

先生の返答:
{teacher_message}
"""
    )

    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "should_save_weak_note": False,
            "weak_note": "",
            "should_save_lesson_report": False,
            "lesson_report": "",
            "next_step": ""
        }


def save_study_learning_notes(thread, user_id, user_message, teacher_message, history):
    if thread is None or thread.thread_type != STUDY_THREAD_TYPE:
        return

    lesson_end = is_study_lesson_end_message(user_message)
    should_extract = (
        should_make_study_weak_note(user_message)
        or lesson_end
        or is_study_summary_action(user_message)
    )

    if not should_extract:
        return

    try:
        note_data = extract_study_learning_notes(
            subject=thread.title,
            user_message=user_message,
            teacher_message=teacher_message,
            history=history,
            lesson_end=lesson_end
        )
    except Exception:
        return

    weak_note = (note_data.get("weak_note") or "").strip()
    lesson_report = (note_data.get("lesson_report") or "").strip()
    next_step = (note_data.get("next_step") or "").strip()

    if note_data.get("should_save_weak_note") and weak_note:
        save_or_update_memory(
            content=f"{thread.title}の苦手ノート: {weak_note}",
            category="weak_area",
            importance=5,
            confidence=0.86,
            source_type="user_statement",
            status="confirmed",
            user_id=user_id
        )

    if note_data.get("should_save_lesson_report") and lesson_report:
        save_or_update_memory(
            content=f"{thread.title}の学習レポート: {lesson_report}",
            category="lesson_report",
            importance=4,
            confidence=0.82,
            source_type="ai_inference",
            status="confirmed",
            user_id=user_id
        )

    if next_step:
        save_or_update_memory(
            content=f"{thread.title}の次回の一歩: {next_step}",
            category="next_step",
            importance=4,
            confidence=0.8,
            source_type="ai_inference",
            status="confirmed",
            user_id=user_id
        )


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
- 「いい質問だね」「ここは最初つまずきやすいところだよ」のように、安心できる先生の入り方をしてください。
- 基本の授業の流れは、説明 → 理解確認 → 必要なら小さな応用問題 → 添削 → 今日のまとめ、です。
- ただし毎回すべてを詰め込まず、ユーザーの発言に合う段階だけを行ってください。
- 説明が必要な時は、結論、たとえ、短い例、理解確認の順にしてください。
- ユーザーが答えた時は、まず正誤をやさしく伝え、どこが良いか・どこを直すかを短く添削してください。
- 理解確認や問題を出す時は、一度に1問だけにしてください。
- 「理解確認」と言われたら、今の内容から1問だけ出し、答えやすい形にしてください。
- 「応用問題」と言われたら、少しだけ難しい1問を出し、必要ならヒントを1つ添えてください。
- 授業中の一時理解度を見て、理解できている内容は繰り返し説明しすぎず、次の内容へ少し進めてください。
- 同じ問題や似すぎた問題を何度も出さないでください。復習が必要な場合も、問題文・状況・出題方法を変えてください。
- 問題の難易度は、用語確認 → 記述問題 → コード読解 → コード修正 → コード作成 → ミニアプリ制作、の順に少しずつ上げてください。
- ユーザーが理解できていると判断できる時は、基礎問題を続けず、実践的な問題へ進めてください。
- ユーザーがつまずいた時は、難易度を下げ、説明を小さく分けてから確認問題に戻ってください。
- 「今日のまとめ」と言われたら、今日やったこと、覚えるポイント、次に復習することを短くまとめてください。
- 「今日はここまで」と言われたら、学習レポートとして「できたこと」「まだ曖昧なこと」「次回やること」を短く整理し、最後に労う一言を添えてください。
- 学習レポートでは、次回の最初に何をすればよいかが分かる1文を必ず入れてください。
- 分からないと言われた時は、まず「どこで止まったか」を先生側で言語化し、言い換え・具体例・小さいステップに分けてください。
- 分からない内容が複数ありそうな時は、全部を広げず、いま一番大事なつまずきだけ扱ってください。
- 画像問題では、読み取れた内容 → 何を問われているか → 解き方の小さい手順 → 理解確認1問、の順にしてください。
- 画像の文字が読みにくい時は、推測で断定せず「ここは読み取りが怪しい」と伝えて確認してください。
- ユーザーの苦手、理解度、好きな説明方法、前回の続き、テスト日、提出期限を自然に使ってください。
- 「前にこの科目をやった日」「久しぶりかどうか」「テストまでの日数」が分かる時は、自然に学習ペースへ反映してください。
- 勉強以外の人生相談、健康管理、日記、予定管理、Goal Plannerの話へ広げすぎないでください。
- 最後は必要に応じて「ここまで分かる？」のような理解確認を1つだけ入れてください。
"""


def build_subject_specialist_rules(subject):
    subject_text = (subject or "").lower()

    if "python" in subject_text:
        return """
Python教育専門の先生として教えてください。
- まず何のための文法かを、日常のたとえで説明してください。
- コード例は短くし、1行ずつ意味を説明してください。
- エラー相談では、原因 → 確認場所 → 直し方の順にしてください。
- 必要なら、最後に1問だけ小さな練習問題を出してください。
"""

    if "java" in subject_text:
        return """
Java教育専門の先生として教えてください。
- 型、クラス、メソッド、オブジェクトの関係を丁寧に分けて説明してください。
- コード例は短くし、どこがJavaらしい考え方かを補足してください。
- コンパイルエラーは、エラー文の読み方から一緒に整理してください。
"""

    if "数学" in subject_text or "math" in subject_text:
        return """
数学専門の先生として教えてください。
- 公式だけを出さず、なぜその式になるのかを途中式で説明してください。
- 計算は一段ずつ進め、飛ばしすぎないでください。
- 最後に似た形の確認問題を1問だけ出してください。
"""

    if "英語" in subject_text or "toeic" in subject_text:
        return """
英語専門の先生として教えてください。
- 文法は日本語の感覚との違いを使って説明してください。
- 単語や表現は、短い例文を必ず1つ添えてください。
- TOEICの場合は、頻出パターンと解く順番も意識してください。
"""

    if "基本情報" in subject_text or "情報" in subject_text:
        return """
情報処理試験の先生として教えてください。
- 用語暗記だけでなく、試験でどう問われるかを意識して説明してください。
- 最後に一問一答形式の確認を1つ入れてください。
- 計算問題は、式と考え方を分けて説明してください。
"""

    if "歴史" in subject_text:
        return """
歴史専門の先生として教えてください。
- 年号暗記だけでなく、原因 → 出来事 → 結果の流れで説明してください。
- 人物や出来事のつながりを短く整理してください。
- 最後に「なぜそうなったか」を確認する質問を1つ出してください。
"""

    return """
この科目の専門の先生として教えてください。
- 専門用語はかみ砕いて説明してください。
- ユーザーの理解度に合わせて、例・言い換え・確認問題を使ってください。
- 一度に詰め込みすぎず、次に答えられる小さな問いを1つ出してください。
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

科目別の教え方:
{build_subject_specialist_rules(thread_title)}
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
        "can_delete": thread.thread_type != DIARY_THREAD_TYPE,
        "has_roadmap": has_active_roadmap_for_thread(thread)
    }

    if thread.thread_type == STUDY_THREAD_TYPE:
        thread_data["study_context"] = serialize_study_context(thread)

    return thread_data


def prepare_ai_response_context(thread, user_id, clean_message):
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

    study_context_text = (
        build_study_context_for_prompt(thread, user_id, clean_message)
        if is_study_thread
        else ""
    )
    prompt = build_ai_prompt(
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
        study_context_text
    )

    return {
        "thread": thread,
        "history": history,
        "prompt": prompt,
        "is_study_thread": is_study_thread
    }


def process_chat_message(thread, user_id, clean_message):
    context = prepare_ai_response_context(thread, user_id, clean_message)
    thread = context["thread"]
    history = context["history"]
    is_study_thread = context["is_study_thread"]
    ai_message = ""
    should_save_ai_message = True

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=context["prompt"]
        )

        ai_message = response.output_text
    except Exception:
        ai_message = "PASの回答を生成できませんでした。もう一度送信してください。"
        should_save_ai_message = False

    if should_save_ai_message:
        save_message("assistant", ai_message, thread.id, user_id)

        if is_study_thread:
            save_study_learning_notes(
                thread=thread,
                user_id=user_id,
                user_message=clean_message,
                teacher_message=ai_message,
                history=history
            )
            record_lesson_problem_history(thread, user_id, ai_message)

    chat_items = load_chat_items(thread.id, user_id)

    if not should_save_ai_message:
        chat_items.append({
            "role": "assistant",
            "content": ai_message,
            "created_at": app_now()
        })

    return chat_items


def sse_event(event_name, data):
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def extract_stream_delta(event):
    event_type = getattr(event, "type", "")

    if event_type == "response.output_text.delta":
        return getattr(event, "delta", "") or ""

    if event_type.endswith(".delta"):
        delta = getattr(event, "delta", "")

        if isinstance(delta, str):
            return delta

    return ""


def stream_chat_message_events(thread, user_id, clean_message):
    context = prepare_ai_response_context(thread, user_id, clean_message)
    thread = context["thread"]
    history = context["history"]
    is_study_thread = context["is_study_thread"]
    ai_parts = []
    saved = False

    try:
        yield sse_event("ready", {"ok": True})

        with client.responses.stream(
            model="gpt-4.1-mini",
            input=context["prompt"]
        ) as stream:
            for event in stream:
                delta = extract_stream_delta(event)

                if not delta:
                    continue

                ai_parts.append(delta)
                yield sse_event("delta", {"text": delta})
    except GeneratorExit:
        raise
    except Exception:
        if not ai_parts:
            yield sse_event(
                "error",
                {"message": "PASの回答を生成できませんでした。もう一度送信してください。"}
            )
        return
    finally:
        ai_message = "".join(ai_parts).strip()

        if ai_message and not saved:
            save_message("assistant", ai_message, thread.id, user_id)
            saved = True

            if is_study_thread:
                save_study_learning_notes(
                    thread=thread,
                    user_id=user_id,
                    user_message=clean_message,
                    teacher_message=ai_message,
                    history=history
                )
                record_lesson_problem_history(thread, user_id, ai_message)

    yield sse_event("done", {"ok": True})


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
    study_context_text = build_study_context_for_prompt(thread, user_id, prompt_message) if is_study_thread else ""
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
                            ) + """

画像授業の追加ルール:
1. まず画像から読み取れた内容を短く整理してください。
2. 問題なら「何を問われているか」を先に説明してください。
3. 解き方を小さい手順に分けてください。
4. 答えだけで終わらず、最後に理解確認を1問だけ出してください。
5. 読み取れない部分は推測で断定せず、ユーザーに確認してください。
"""
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

        if is_study_thread:
            save_study_learning_notes(
                thread=thread,
                user_id=user_id,
                user_message=user_message,
                teacher_message=ai_message,
                history=history
            )
            record_lesson_problem_history(thread, user_id, ai_message)

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


@app.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="forgot_password.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "",
            "message": "",
            "reset_url": "",
            "email": ""
        }
    )


@app.post("/forgot-password")
def forgot_password_action(request: Request, email: str = Form("")):
    clean_email = normalize_email(email)
    token = create_password_reset_token(clean_email)
    reset_url = ""
    email_sent = False

    if token:
        reset_url = f"{build_base_url(request)}/reset-password?token={token}"
        email_sent = send_password_reset_email(clean_email, reset_url)

    message = "入力されたメールアドレスに再設定リンクを送信しました。"

    if token and not email_sent:
        message = "メール送信設定が未設定のため、開発用の再設定リンクを表示しています。"

    return templates.TemplateResponse(
        request=request,
        name="forgot_password.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "",
            "message": message,
            "reset_url": reset_url if token and not email_sent else "",
            "email": clean_email
        }
    )


@app.get("/reset-password")
def reset_password_page(request: Request, token: str = ""):
    token_data = load_valid_password_reset_token(token)

    return templates.TemplateResponse(
        request=request,
        name="reset_password.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "" if token_data else "この再設定リンクは無効、または期限切れです。",
            "message": "",
            "token": token if token_data else "",
            "email": token_data["email"] if token_data else ""
        }
    )


@app.post("/reset-password")
def reset_password_action(
    request: Request,
    token: str = Form(""),
    password: str = Form("")
):
    token_data = load_valid_password_reset_token(token)

    if token_data is None:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={
                "settings": {"theme_name": "calm"},
                "error": "この再設定リンクは無効、または期限切れです。",
                "message": "",
                "token": "",
                "email": ""
            }
        )

    if not reset_user_password(token, password):
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={
                "settings": {"theme_name": "calm"},
                "error": f"パスワードは{PASSWORD_MIN_LENGTH}文字以上にしてください。",
                "message": "",
                "token": token,
                "email": token_data["email"]
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="reset_password.html",
        context={
            "settings": {"theme_name": "calm"},
            "error": "",
            "message": "パスワードを変更しました。ログインできます。",
            "token": "",
            "email": token_data["email"]
        }
    )


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
    active_threads = [
        thread for thread in study_threads
        if thread["study_context"].get("session_count", 0) > 0
    ]

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
        "study_threads": study_threads,
        "next_study_thread": active_threads[0] if active_threads else (study_threads[0] if study_threads else None),
        "recent_study_history": load_recent_study_history(current_user.id),
        "memory_highlights": load_study_memory_highlights(current_user.id)
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


@app.post("/api/chat/{thread_id}/messages/stream")
def api_chat_message_stream(request: Request, thread_id: int, payload: ChatMessageCreatePayload):
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

    return StreamingResponse(
        stream_chat_message_events(thread, current_user.id, clean_message),
        media_type="text/event-stream"
    )


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
def api_chat_thread_delete(request: Request, thread_id: int, delete_roadmap: bool = False):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    delete_chat_thread(thread_id, current_user.id, delete_roadmap=delete_roadmap)
    return {"ok": True}


@app.get("/api/bookshelves")
def api_bookshelves(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    return {
        "bookshelves": load_bookshelves(current_user.id)
    }


@app.get("/api/bookshelves/{subject}")
def api_bookshelf(request: Request, subject: str):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    return load_bookshelf(subject, current_user.id)


@app.get("/api/roadmaps")
def api_roadmaps(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    return {
        "subjects": load_roadmap_overview(current_user.id)
    }


@app.delete("/api/roadmaps")
def api_roadmap_delete(request: Request, payload: RoadmapDeletePayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    subject = normalize_subject_title(payload.subject)

    if not subject:
        return JSONResponse({"error": "subject_required"}, status_code=400)

    result = delete_study_roadmap(current_user.id, subject, payload.thread_id)

    return {
        "ok": True,
        "result": result
    }


@app.get("/api/textbooks/{textbook_id}")
def api_textbook_detail(request: Request, textbook_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    textbook = load_textbook(textbook_id, current_user.id)

    if textbook is None:
        return JSONResponse({"error": "textbook_not_found"}, status_code=404)

    return {
        "textbook": textbook
    }


@app.post("/api/chat/{thread_id}/textbook_preview")
def api_textbook_preview(request: Request, thread_id: int, payload: TextbookPreviewPayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    thread = load_chat_thread(thread_id, current_user.id)

    if thread is None:
        return JSONResponse({"error": "thread_not_found"}, status_code=404)

    if thread.thread_type != STUDY_THREAD_TYPE:
        return JSONResponse({"error": "study_thread_required"}, status_code=400)

    preview = create_textbook_preview(thread, current_user.id, payload.source_note)

    return {
        "preview": preview
    }


@app.post("/api/textbooks/confirm")
def api_textbook_confirm(request: Request, payload: TextbookConfirmPayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    textbook = confirm_textbook_preview(payload, current_user.id)

    if textbook is None:
        return JSONResponse({"error": "textbook_save_failed"}, status_code=400)

    return {
        "textbook": textbook
    }


@app.post("/api/textbooks/{textbook_id}/answers")
def api_textbook_answer(request: Request, textbook_id: int, payload: TextbookAnswerPayload):
    current_user = get_current_user(request)

    if current_user is None:
        return JSONResponse({"error": "login_required"}, status_code=401)

    result = submit_textbook_answer(textbook_id, current_user.id, payload)

    if result is None:
        return JSONResponse({"error": "answer_submit_failed"}, status_code=400)

    return result


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


@app.get("/bookshelves")
def bookshelves_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return render_react_app(request, current_user)


@app.get("/bookshelf/{subject}")
def bookshelf_page(request: Request, subject: str):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return render_react_app(request, current_user)


@app.get("/roadmaps")
def roadmaps_page(request: Request):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return render_react_app(request, current_user)


@app.get("/textbook/{textbook_id}")
def textbook_page(request: Request, textbook_id: int):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

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
def chat_thread_delete(request: Request, thread_id: int, delete_roadmap: bool = Form(False)):
    current_user = get_current_user(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    delete_chat_thread(thread_id, current_user.id, delete_roadmap=delete_roadmap)

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
