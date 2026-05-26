# -*- coding: utf-8 -*-
"""Tradução de notícias para português via Gemini."""

import json
import re
import sys
import time

from google import genai

from .config import GEMINI_API_KEY, GEMINI_MODEL, TRANSLATE_BATCH_SIZE, get_active_model
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

    MAX_RETRIES = 3
    INITIAL_BACKOFF = 5  # segundos

    def __init__(self, api_key: str | None = None):
        key = api_key or self._load_active_key() or GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY não configurada.")
        self._api_key = key
        self._client = genai.Client(api_key=key)

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

    def reload_key(self, api_key: str):
        """Recarrega o cliente com uma nova API key."""
        self._api_key = api_key
        self._client = genai.Client(api_key=api_key)

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
        """Traduz um batch de itens com retry automático para erros 429."""
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

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=get_active_model(),
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
                return  # Sucesso — sair do loop de retry

            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Se for erro 429 (rate limit), fazer retry com backoff
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    # Extrair tempo de retry sugerido se disponível
                    retry_match = re.search(r"retryDelay.*?(\d+)s", error_str)
                    wait_time = int(retry_match.group(1)) if retry_match else self.INITIAL_BACKOFF * (2 ** attempt)
                    wait_time = min(wait_time, 60)  # Cap em 60s
                    
                    print(f"[Tradutor] Limite de taxa atingido. Aguardando {wait_time}s antes do retry {attempt + 1}/{self.MAX_RETRIES}...", file=sys.stderr)
                    time.sleep(wait_time)
                    continue
                else:
                    # Erro não-recuperável, sair imediatamente
                    print(f"[Tradutor] Erro na tradução: {e}", file=sys.stderr)
                    break

        # Todas as tentativas falharam — manter originais
        print(f"[Tradutor] Tradução falhou após {self.MAX_RETRIES} tentativas: {last_error}", file=sys.stderr)
        for item in batch:
            item.titulo_pt = item.titulo
            item.lead_pt = item.lead
