# -*- coding: utf-8 -*-
"""Modelos de dados centrais."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    """Representa um veículo de notícias."""
    nome: str
    pais: str
    afiliacao: str
    url: str
    idioma: str
    estrategia: str  # "rss", "scraping", "llm"
    rss_url: str | None = None
    grupo: str = ""
    circulacao: str = ""

    @property
    def id(self) -> str:
        """Identificador normalizado para busca."""
        return self.nome.lower().strip()


@dataclass
class NewsItem:
    """Representa uma notícia individual."""
    titulo: str
    titulo_pt: str | None = None
    lead: str = ""
    lead_pt: str | None = None
    link: str = ""
    data: datetime | None = None
    fonte: str = ""
    pais: str = ""
    posicao: int = 0  # Posição no feed/homepage (para ranking)

    @property
    def titulo_display(self) -> str:
        """Retorna título em PT se disponível, senão original."""
        return self.titulo_pt or self.titulo

    @property
    def lead_display(self) -> str:
        """Retorna lead em PT se disponível, senão original."""
        return self.lead_pt or self.lead


@dataclass
class FetchResult:
    """Resultado de uma busca de notícias."""
    fonte: Source
    itens: list[NewsItem] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    estrategia_usada: str = ""
    sucesso: bool = False
    erro: str | None = None
