# -*- coding: utf-8 -*-
"""Configuração da aplicação."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carregar .env do diretório raiz do projeto
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# ── Caminhos ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = _project_root
CSV_PATH = _project_root / "Principais noticiarios do mundo - Noticiários gerais.csv"
SOURCES_CONFIG_PATH = _project_root / "sources_config.json"

# ── HTTP ──────────────────────────────────────────────────────────────────────
HTTP_TIMEOUT = 15  # segundos
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_LIMIT = 15  # Número padrão de notícias retornadas
DEFAULT_MODE = "manchetes"
TRANSLATE_BATCH_SIZE = 10  # Itens por chamada de tradução

# ── Idiomas ───────────────────────────────────────────────────────────────────
COUNTRY_LANGUAGE = {
    "EUA": "en", "China": "zh", "Alemanha": "de", "Reino Unido": "en",
    "França": "fr", "Espanha": "es", "Itália": "it", "Brasil": "pt",
    "Argentina": "es", "México": "es", "Colômbia": "es", "Chile": "es",
    "Peru": "es", "Paraguai": "es", "Uruguai": "es", "Rússia": "ru",
    "África do Sul": "en", "Nigéria": "en", "Quênia": "en", "Egito": "ar",
    "Índia": "en", "Japão": "ja", "Austrália": "en", "Catar": "en",
    "Israel": "he", "Arábia Saudita": "ar", "Emirados Árabes": "en",
    "Irã": "fa", "Turquia": "tr", "Paquistão": "en", "Cazaquistão": "en",
    "Uzbequistão": "en", "Afeganistão": "en", "Indonésia": "id",
    "Filipinas": "en", "Tailândia": "en", "Malásia": "en",
    "Ucrânia": "uk", "Sérvia": "sr", "Geórgia": "en",
}
