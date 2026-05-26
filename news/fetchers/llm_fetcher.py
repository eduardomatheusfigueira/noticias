# -*- coding: utf-8 -*-
"""Fetcher de notícias via LLM (Gemini) como fallback universal."""

import json
import re

import requests
from bs4 import BeautifulSoup
from google import genai

from ..config import GEMINI_API_KEY, GEMINI_MODEL, HTTP_HEADERS, HTTP_TIMEOUT
from ..models import Source, NewsItem, FetchResult
from .base import BaseFetcher


_EXTRACT_PROMPT = """Você é um assistente que extrai manchetes de páginas de notícias.
Dado o texto abaixo (extraído da homepage de "{source_name}" — {source_country}), 
extraia as {limit} principais manchetes/notícias.

Para cada notícia, retorne em JSON:
- "titulo": título da notícia (no idioma original)
- "lead": breve descrição em 1-2 frases (se disponível, senão string vazia)
- "link": URL da notícia (se disponível, senão string vazia)

Retorne APENAS um array JSON válido, sem markdown, sem explicações.
Exemplo: [{{"titulo": "...", "lead": "...", "link": "..."}}]

TEXTO DA PÁGINA:
{page_text}
"""


class LLMFetcher(BaseFetcher):
    """Usa Gemini para extrair manchetes de páginas de notícias."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY não configurada. Verifique o arquivo .env")
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    # URLs alternativas para sites cujo domínio principal não funciona bem
    _ALT_URLS = {
        "people.cn": "http://en.people.cn/",
        "people.com.cn": "http://en.people.cn/",
        "cankaoxiaoxi.com": "http://en.people.cn/",  # Reference News
        "yomiuri.co.jp": "https://japannews.yomiuri.co.jp/",
        "asahi.com": "https://www.asahi.com/ajw/",
        "mainichi.jp": "https://mainichi.jp/english/",
        "kompas.com": "https://english.kompas.com/",
        "ahram.org.eg": "https://english.ahram.org.eg/",
    }

    def _get_url(self, source: Source) -> str:
        """Retorna a melhor URL para acessar a fonte."""
        from urllib.parse import urlparse
        domain = urlparse(source.url).netloc.replace("www.", "")
        return self._ALT_URLS.get(domain, source.url)

    def fetch(self, source: Source, limit: int = 15) -> FetchResult:
        try:
            # 1. Buscar a homepage (com URL alternativa se disponível)
            url = self._get_url(source)
            page_text = self._fetch_page_text(url)
            if not page_text:
                # Tentar URL original se alternativa falhou
                if url != source.url:
                    page_text = self._fetch_page_text(source.url)
            if not page_text:
                return FetchResult(
                    fonte=source,
                    estrategia_usada="llm",
                    sucesso=False,
                    erro="Não foi possível acessar a homepage para extração via LLM.",
                )

            # 2. Enviar ao Gemini
            prompt = _EXTRACT_PROMPT.format(
                source_name=source.nome,
                source_country=source.pais,
                limit=limit,
                page_text=page_text[:15000],
            )

            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            # 3. Parsear resposta JSON
            itens = self._parse_response(response.text, source)

            return FetchResult(
                fonte=source,
                itens=itens[:limit],
                estrategia_usada="llm",
                sucesso=len(itens) > 0,
                erro=None if itens else "LLM não retornou manchetes válidas.",
            )

        except Exception as e:
            return FetchResult(
                fonte=source,
                estrategia_usada="llm",
                sucesso=False,
                erro=f"Erro no LLM Fetcher: {e}",
            )

    def _fetch_page_text(self, url: str) -> str | None:
        """Busca a homepage e extrai texto limpo."""
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                # Tentar sem headers customizados
                resp = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Remover scripts, styles
            for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
                tag.decompose()

            # Extrair texto
            text = soup.get_text(separator="\n", strip=True)

            # Limpar linhas vazias e espaços excessivos
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines)

        except Exception:
            return None

    def _parse_response(self, response_text: str, source: Source) -> list[NewsItem]:
        """Parseia a resposta JSON do LLM."""
        # Remover blocos markdown se presentes
        cleaned = re.sub(r"```(?:json)?\s*", "", response_text)
        cleaned = cleaned.strip()

        # Extrair JSON array
        json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            # Tentar limpar caracteres problemáticos
            try:
                cleaned_json = json_match.group().replace("\n", " ")
                data = json.loads(cleaned_json)
            except json.JSONDecodeError:
                return []

        itens = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            # Aceitar tanto 'titulo' quanto 'title' como chave
            titulo = (item.get("titulo") or item.get("title", "")).strip()
            if not titulo:
                continue
            lead = (item.get("lead") or item.get("description") or item.get("summary", "")).strip()
            link = (item.get("link") or item.get("url", "")).strip()
            itens.append(NewsItem(
                titulo=titulo,
                lead=lead,
                link=link,
                fonte=source.nome,
                pais=source.pais,
                posicao=i,
            ))

        return itens
