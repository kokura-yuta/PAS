from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

Base = declarative_base()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

class ChatMessage(Base):
    __tablename__="chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(20))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def save_message(role, content):
    db = SessionLocal()

    new_message = ChatMessage(
        role=role,
        content=content
    )

    db.add(new_message)
    db.commit()
    db.close()

def load_messages():
    db = SessionLocal()

    messages = db.query(ChatMessage).order_by(ChatMessage.created_at).all()

    history =""

    for msg in messages:
        history += f"{msg.role}: {msg.content}\n"
    
    db.close()

    return history

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

PAS_PERSONAS = {
    "friend": """
あなたはPASです。
友達のように自然で、相談しやすい口調で返して下さい。
説教っぽくせずに、相手に寄り添って下さい。
"""
}

def build_ai_prompt(message, history, persona="friend"):
    persona_prompt = PAS_PERSONAS[persona]

    return f"""
{persona_prompt}

これまでの会話:
{history}

ユーザーの今回の発言:
{message}
"""

app = FastAPI()

templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={}
    )

@app.get("/chat")
def chat_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html"
    )
@app.post("/chat")
def chat_send(request: Request, message: str = Form(...)):
    history = load_messages()

    save_message("user", message)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=build_ai_prompt(message, history)
    )

    ai_message = response.output_text

    save_message("assistant", ai_message)
    
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "message": message,
            "ai_message": ai_message
            }
    )
