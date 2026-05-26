# -*- coding: utf-8 -*-
"""Registro de fontes de notícias — carrega CSV + config e permite busca."""

import csv
import json
from pathlib import Path

from .config import CSV_PATH, SOURCES_CONFIG_PATH, COUNTRY_LANGUAGE
from .models import Source

# Mapeamento de código de idioma para nome legível
_LANG_NAMES = {
    "pt": "Português", "en": "Inglês", "es": "Espanhol", "fr": "Francês",
    "de": "Alemão", "it": "Italiano", "ru": "Russo", "ar": "Árabe",
    "zh": "Chinês", "ja": "Japonês", "ko": "Coreano", "hi": "Hindi",
    "tr": "Turco", "fa": "Persa", "uk": "Ucraniano", "sr": "Sérvio",
    "ka": "Georgiano", "id": "Indonésio", "tl": "Filipino", "th": "Tailandês",
    "ms": "Malaio", "ur": "Urdu", "he": "Hebraico",
}


class SourceRegistry:
    """Carrega e gerencia todas as fontes de notícias."""

    def __init__(self):
        self._sources: list[Source] = []
        self._by_name: dict[str, Source] = {}
        self._load()

    def _load(self):
        """Carrega CSV + sources_config.json."""
        # Carregar config de estratégias
        config = {}
        if SOURCES_CONFIG_PATH.exists():
            with open(SOURCES_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)

        # Carregar CSV
        if not CSV_PATH.exists():
            raise FileNotFoundError(f"CSV não encontrado: {CSV_PATH}")

        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nome = row["Jornal/Agência"]
                pais = row["País"]
                url = row["Link"].strip()
                if not url.startswith("http"):
                    url = "https://" + url

                # Determinar idioma
                lang_code = COUNTRY_LANGUAGE.get(pais, "en")
                idioma = _LANG_NAMES.get(lang_code, lang_code)

                # Buscar config de estratégia
                src_config = config.get(nome, {})
                estrategia = src_config.get("estrategia", "scraping")
                rss_url = src_config.get("rss_url")

                source = Source(
                    nome=nome,
                    pais=pais,
                    afiliacao=row.get("Afiliação Política", ""),
                    url=url,
                    idioma=idioma,
                    estrategia=estrategia,
                    rss_url=rss_url,
                    grupo=row.get("Grupo Controlador/Donos", ""),
                    circulacao=row.get("Circulação Estimada", ""),
                )
                self._sources.append(source)
                self._by_name[source.id] = source

    @property
    def all(self) -> list[Source]:
        """Todas as fontes."""
        return self._sources

    @staticmethod
    def _normalize(text: str) -> str:
        """Remove acentos e normaliza para busca."""
        import unicodedata
        nfkd = unicodedata.normalize("NFKD", text.lower().strip())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def buscar(self, termo: str) -> list[Source]:
        """Busca fontes por nome parcial (case-insensitive, ignora acentos)."""
        termo_norm = self._normalize(termo)
        results = []
        for src in self._sources:
            nome_norm = self._normalize(src.nome)
            pais_norm = self._normalize(src.pais)
            if termo_norm in nome_norm or termo_norm in pais_norm:
                results.append(src)
        return results

    def por_nome(self, nome: str) -> Source | None:
        """Busca fonte por nome exato (case-insensitive)."""
        return self._by_name.get(nome.lower().strip())

    def por_pais(self, pais: str) -> list[Source]:
        """Retorna fontes de um país."""
        pais = pais.lower().strip()
        return [s for s in self._sources if s.pais.lower() == pais]

    def por_estrategia(self, estrategia: str) -> list[Source]:
        """Retorna fontes por tipo de estratégia."""
        return [s for s in self._sources if s.estrategia == estrategia]

    def paises(self) -> list[str]:
        """Lista de países únicos."""
        return sorted(set(s.pais for s in self._sources))
