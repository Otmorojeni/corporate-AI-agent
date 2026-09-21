from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router

app = FastAPI(
    title="Corporate Abbreviation Assistant API",
    version="1",
    description=(
        "Ответы по базе знаний с использованием самостоятельно извлечённых из PDF "
        "аббревиатур для понимания запросов и выбора значения по контексту."
    ),
)

# CORS middleware for Web UI (Streamlit, React, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include official routes
app.include_router(router)
