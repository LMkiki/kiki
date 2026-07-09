import os

import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api import app
from database import get_engine
from models import Base

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=get_engine())


@app.get("/chat")
@app.get("/chat.html")
def chat_page():
    return FileResponse(os.path.join(PARENT_DIR, "chat.html"))


@app.get("/admin")
@app.get("/admin.html")
def admin_page():
    return FileResponse(os.path.join(PARENT_DIR, "admin.html"))


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
