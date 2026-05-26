# -*- coding: utf-8 -*-
"""Tradução de notícias para português via Gemini."""

import json
import re

from google import genai

from .config import GEMINI_API_KEY, GEMINI_MODEL, TRANSLATE_BATCH_SIZE
from .models import NewsItem


_TRANSLATE_PROMPT = """Traduza os seguintes títulos e leads de notícias para português brasileiro.
Mantenha tom jornalístico, conciso e natural. Não adicione informações.

Retorne APENAS um array JSON com os campos "titulo_pt" e "lead_pt" para cada item, na mesma ordem.
Exemplo: [{{"titulo_pt": "...", "lead_pt": "..."}}]

ITENS PARA TRADUZIR:
{items_json}
"""


class Translator:
    """Traduz notícias para português brasileiro via Gemini."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY não configurada.")
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    def traduzir(self, itens: list[NewsItem], idioma_fonte: str = "") -> list[NewsItem]:
        """Traduz uma lista de NewsItems para português.
        
        Pula tradução se idioma_fonte == 'Português'.
        Processa em batches para não exceder limites do modelo.
        """
        if idioma_fonte == "Português":
            # Já está em PT, copiar titulo/lead para os campos _pt
            for item in itens:
                item.titulo_pt = item.titulo
                item.lead_pt = item.lead
            return itens

        # Processar em batches
        for i in range(0, len(itens), TRANSLATE_BATCH_SIZE):
            batch = itens[i:i + TRANSLATE_BATCH_SIZE]
            self._traduzir_batch(batch)

        return itens

    def _traduzir_batch(self, batch: list[NewsItem]):
        """Traduz um batch de itens."""
        # Preparar dados para o prompt
        items_data = []
        for item in batch:
            items_data.append({
                "titulo": item.titulo,
                "lead": item.lead[:300] if item.lead else "",
            })

        prompt = _TRANSLATE_PROMPT.format(
            items_json=json.dumps(items_data, ensure_ascii=False, indent=2)
        )

        try:
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            # Parsear resposta
            json_match = re.search(r"\[.*\]", response.text, re.DOTALL)
            if not json_match:
                # Fallback: manter originais
                for item in batch:
                    item.titulo_pt = item.titulo
                    item.lead_pt = item.lead
                return

            translations = json.loads(json_match.group())

            for item, trad in zip(batch, translations):
                if isinstance(trad, dict):
                    item.titulo_pt = trad.get("titulo_pt", item.titulo)
                    item.lead_pt = trad.get("lead_pt", item.lead)
                else:
                    item.titulo_pt = item.titulo
                    item.lead_pt = item.lead

        except Exception:
            # Em caso de erro, manter originais
            for item in batch:
                item.titulo_pt = item.titulo
                item.lead_pt = item.lead
