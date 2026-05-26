# -*- coding: utf-8 -*-
"""Classificação de notícias em 4 modos."""

import json
import re

from google import genai

from .config import GEMINI_API_KEY, GEMINI_MODEL, get_active_model
from .models import NewsItem


_RESUMO_PROMPT = """Você é um editor de um boletim jornalístico em português brasileiro.
Dado as seguintes manchetes do veículo "{source_name}" ({source_country}), 
faça um resumo conciso das {n} notícias mais importantes do dia.

Formato: Um boletim curto e direto, com cada notícia em 1-2 frases.
Use tom jornalístico profissional. Escreva tudo em português brasileiro.

MANCHETES:
{headlines}
"""


class Classifier:
    """Classifica e ordena notícias em diferentes modos."""

    def __init__(self):
        self._gemini_client = None

    def _get_gemini(self):
        """Inicializa cliente Gemini sob demanda."""
        if self._gemini_client is None:
            key = self._load_active_key() or GEMINI_API_KEY
            if not key:
                raise ValueError("GEMINI_API_KEY necessária para o modo 'resumo'.")
            self._gemini_client = genai.Client(api_key=key)
        return self._gemini_client

    @staticmethod
    def _load_active_key() -> str | None:
        """Tenta carregar a chave ativa do gerenciador de API keys."""
        try:
            from pathlib import Path
            keys_file = Path(__file__).parent.parent / "api_keys.json"
            if keys_file.exists():
                data = json.loads(keys_file.read_text(encoding="utf-8"))
                active = data.get("active", "")
                for entry in data.get("keys", []):
                    if entry.get("label") == active:
                        return entry.get("key", "")
        except Exception:
            pass
        return None

    def classificar(self, itens: list[NewsItem], modo: str, 
                     source_name: str = "", source_country: str = "",
                     limite: int = 15) -> list[NewsItem] | str:
        """Classifica os itens segundo o modo escolhido.
        
        Args:
            itens: Lista de notícias.
            modo: 'manchetes', 'recentes', 'top', ou 'resumo'.
            source_name: Nome da fonte (para resumo).
            source_country: País da fonte (para resumo).
            limite: Número máximo de itens.
            
        Returns:
            Lista de NewsItem (para manchetes/recentes/top) ou str (para resumo).
        """
        if modo == "manchetes":
            return self._manchetes(itens, limite)
        elif modo == "recentes":
            return self._recentes(itens, limite)
        elif modo == "top":
            return self._top(itens, limite)
        elif modo == "resumo":
            return self._resumo(itens, source_name, source_country, limite)
        else:
            return self._manchetes(itens, limite)

    def _manchetes(self, itens: list[NewsItem], limite: int) -> list[NewsItem]:
        """Retorna na ordem original do feed/homepage (ordem editorial)."""
        return sorted(itens, key=lambda x: x.posicao)[:limite]

    def _recentes(self, itens: list[NewsItem], limite: int) -> list[NewsItem]:
        """Ordena por data de publicação (mais recentes primeiro)."""
        # Itens com data primeiro, depois sem data
        com_data = [i for i in itens if i.data is not None]
        sem_data = [i for i in itens if i.data is None]
        com_data.sort(key=lambda x: x.data, reverse=True)
        return (com_data + sem_data)[:limite]

    def _top(self, itens: list[NewsItem], limite: int) -> list[NewsItem]:
        """Scoring heurístico para identificar as mais importantes."""
        scored = []
        for item in itens:
            score = 0
            # Posição baixa (mais no topo) = mais importante
            score += max(0, 20 - item.posicao * 2)
            # Tem lead = mais substancial
            if item.lead and len(item.lead) > 50:
                score += 10
            # Título longo = mais descritivo (provavelmente manchete principal)
            if len(item.titulo) > 50:
                score += 5
            elif len(item.titulo) > 30:
                score += 3
            # Tem data = mais completo
            if item.data:
                score += 3
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored][:limite]

    def _resumo(self, itens: list[NewsItem], source_name: str, 
                source_country: str, n: int = 5) -> str:
        """Gera resumo inteligente via LLM."""
        client = self._get_gemini()

        # Preparar lista de manchetes
        headlines = []
        for item in itens[:20]:  # Enviar até 20 para o LLM escolher
            titulo = item.titulo_pt or item.titulo
            lead = item.lead_pt or item.lead
            entry = f"- {titulo}"
            if lead:
                entry += f": {lead[:150]}"
            headlines.append(entry)

        prompt = _RESUMO_PROMPT.format(
            source_name=source_name,
            source_country=source_country,
            n=min(n, len(itens)),
            headlines="\n".join(headlines),
        )

        try:
            response = client.models.generate_content(
                model=get_active_model(),
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            return f"Erro ao gerar resumo: {e}"
