# -*- coding: utf-8 -*-
"""Fetcher de notícias via RSS/Atom feeds."""

import re
from datetime import datetime

import feedparser
import requests

from ..config import HTTP_HEADERS, HTTP_TIMEOUT
from ..models import Source, NewsItem, FetchResult
from .base import BaseFetcher


class RSSFetcher(BaseFetcher):
    """Busca notícias via RSS/Atom feed usando feedparser."""

    def fetch(self, source: Source, limit: int = 15) -> FetchResult:
        if not source.rss_url:
            return FetchResult(
                fonte=source,
                estrategia_usada="rss",
                sucesso=False,
                erro="Nenhuma URL de RSS configurada para esta fonte.",
            )

        try:
            # Buscar o feed
            resp = requests.get(
                source.rss_url,
                headers=HTTP_HEADERS,
                timeout=HTTP_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()

            # Parsear
            feed = feedparser.parse(resp.content)

            if not feed.entries:
                return FetchResult(
                    fonte=source,
                    estrategia_usada="rss",
                    sucesso=False,
                    erro="Feed RSS vazio (0 itens).",
                )

            # Converter entradas para NewsItem
            itens = []
            for i, entry in enumerate(feed.entries[:limit]):
                # Extrair título
                titulo = (entry.get("title") or "").strip()
                if not titulo:
                    continue

                # Extrair lead/descrição
                lead = entry.get("summary") or entry.get("description") or ""
                lead = re.sub(r"<[^>]+>", "", lead).strip()  # Remover HTML
                lead = lead[:500]  # Limitar tamanho

                # Extrair link
                link = entry.get("link") or ""

                # Extrair data
                data = None
                date_str = entry.get("published") or entry.get("updated") or ""
                if date_str:
                    try:
                        # feedparser já parseia em time_struct
                        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                        if parsed:
                            data = datetime(*parsed[:6])
                    except Exception:
                        pass

                itens.append(NewsItem(
                    titulo=titulo,
                    lead=lead,
                    link=link,
                    data=data,
                    fonte=source.nome,
                    pais=source.pais,
                    posicao=i,
                ))

            return FetchResult(
                fonte=source,
                itens=itens,
                estrategia_usada="rss",
                sucesso=len(itens) > 0,
                erro=None if itens else "Nenhum item válido encontrado no feed.",
            )

        except requests.RequestException as e:
            return FetchResult(
                fonte=source,
                estrategia_usada="rss",
                sucesso=False,
                erro=f"Erro HTTP ao buscar RSS: {e}",
            )
        except Exception as e:
            return FetchResult(
                fonte=source,
                estrategia_usada="rss",
                sucesso=False,
                erro=f"Erro ao processar RSS: {e}",
            )
