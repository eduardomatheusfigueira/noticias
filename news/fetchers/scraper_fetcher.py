# -*- coding: utf-8 -*-
"""Fetcher de notícias via scraping genérico de homepage."""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import HTTP_HEADERS, HTTP_TIMEOUT
from ..models import Source, NewsItem, FetchResult
from .base import BaseFetcher


class ScraperFetcher(BaseFetcher):
    """Extrai manchetes de homepages usando heurísticas genéricas."""

    # Padrões de classe/id que indicam itens de notícia
    _ARTICLE_SELECTORS = [
        "article",
        "[role='article']",
        ".article",
        ".story",
        ".news-item",
        ".headline",
        ".post",
        ".card",
        ".entry",
        ".item",
    ]

    # Padrões de classe/id a EXCLUIR (menus, ads, rodapé)
    _EXCLUDE_PATTERNS = re.compile(
        r"(nav|menu|footer|sidebar|widget|ad-|advert|promo|social|share|comment|related|tag|breadcrumb|search|login|signup|cookie|banner|popup)",
        re.IGNORECASE,
    )

    # Títulos que não são notícias (filtro de conteúdo)
    _JUNK_TITLES = re.compile(
        r"(esqueci.*(senha|password)|entrar|login|cadastr|assine|newsletter|"
        r"cookie|privacidade|termos de uso|fale conosco|sobre n[oó]s|"
        r"sign.?up|sign.?in|subscribe|log.?in|register|forgot|"
        r"política de|meu perfil|minha conta|carrinho|buscar|pesquisar)",
        re.IGNORECASE,
    )

    # URLs que não são notícias
    _JUNK_URLS = re.compile(
        r"(login|signin|signup|register|recuperacao|password|reset|cookie|"
        r"privacy|terms|about|contact|faq|help|search)",
        re.IGNORECASE,
    )

    def fetch(self, source: Source, limit: int = 15) -> FetchResult:
        try:
            resp = requests.get(
                source.url,
                headers=HTTP_HEADERS,
                timeout=HTTP_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            # Remover script, style, nav, footer
            for tag in soup.find_all(["script", "style", "nav", "footer", "aside", "noscript"]):
                tag.decompose()

            itens = []
            seen_titles = set()

            # Estratégia 1: Buscar <article> tags
            articles = soup.find_all("article", limit=limit * 3)
            for i, article in enumerate(articles):
                item = self._extract_from_container(article, source, i)
                if item and item.titulo.lower() not in seen_titles:
                    seen_titles.add(item.titulo.lower())
                    itens.append(item)

            # Estratégia 2: Buscar headings com links (h1, h2, h3) se poucos resultados
            if len(itens) < limit:
                for heading in soup.find_all(["h1", "h2", "h3"], limit=limit * 4):
                    if self._is_excluded(heading):
                        continue
                    link_tag = heading.find("a")
                    if link_tag and link_tag.get("href"):
                        titulo = link_tag.get_text(strip=True)
                        href = urljoin(source.url, link_tag["href"])
                        if len(titulo) < 15 or titulo.lower() in seen_titles:
                            continue
                        if self._JUNK_TITLES.search(titulo) or self._JUNK_URLS.search(href):
                            continue
                        # Tentar pegar lead do parágrafo seguinte
                        lead = ""
                        next_p = heading.find_next("p")
                        if next_p and not self._is_excluded(next_p):
                            lead = next_p.get_text(strip=True)[:300]

                        seen_titles.add(titulo.lower())
                        itens.append(NewsItem(
                            titulo=titulo,
                            lead=lead,
                            link=href,
                            fonte=source.nome,
                            pais=source.pais,
                            posicao=len(itens),
                        ))

            # Estratégia 3: Links com texto substancial em containers de notícias
            if len(itens) < 5:
                for a_tag in soup.find_all("a", href=True, limit=limit * 5):
                    if self._is_excluded(a_tag):
                        continue
                    text = a_tag.get_text(strip=True)
                    if len(text) < 25 or len(text) > 300:
                        continue
                    if text.lower() in seen_titles:
                        continue
                    href = urljoin(source.url, a_tag["href"])
                    # Filtrar links que não parecem notícias
                    if any(x in href.lower() for x in ["/tag/", "/category/", "/author/", "#", "javascript:"]):
                        continue
                    if self._JUNK_TITLES.search(text) or self._JUNK_URLS.search(href):
                        continue
                    seen_titles.add(text.lower())
                    itens.append(NewsItem(
                        titulo=text,
                        link=href,
                        fonte=source.nome,
                        pais=source.pais,
                        posicao=len(itens),
                    ))

            itens = itens[:limit]

            return FetchResult(
                fonte=source,
                itens=itens,
                estrategia_usada="scraping",
                sucesso=len(itens) > 0,
                erro=None if itens else "Nenhuma manchete encontrada via scraping.",
            )

        except requests.RequestException as e:
            return FetchResult(
                fonte=source,
                estrategia_usada="scraping",
                sucesso=False,
                erro=f"Erro HTTP ao acessar homepage: {e}",
            )
        except Exception as e:
            return FetchResult(
                fonte=source,
                estrategia_usada="scraping",
                sucesso=False,
                erro=f"Erro no scraping: {e}",
            )

    def _extract_from_container(self, container, source: Source, position: int) -> NewsItem | None:
        """Extrai NewsItem de um container de artigo."""
        if self._is_excluded(container):
            return None

        # Buscar título: primeiro heading ou link com texto substancial
        titulo = ""
        link = ""
        
        heading = container.find(["h1", "h2", "h3", "h4"])
        if heading:
            titulo = heading.get_text(strip=True)
            a_tag = heading.find("a")
            if a_tag and a_tag.get("href"):
                link = urljoin(source.url, a_tag["href"])

        if not titulo:
            a_tag = container.find("a", href=True)
            if a_tag:
                titulo = a_tag.get_text(strip=True)
                link = urljoin(source.url, a_tag["href"])

        if not titulo or len(titulo) < 15:
            return None
        if self._JUNK_TITLES.search(titulo):
            return None
        if link and self._JUNK_URLS.search(link):
            return None

        # Buscar lead
        lead = ""
        p_tag = container.find("p")
        if p_tag:
            lead = p_tag.get_text(strip=True)[:300]

        return NewsItem(
            titulo=titulo,
            lead=lead,
            link=link,
            fonte=source.nome,
            pais=source.pais,
            posicao=position,
        )

    def _is_excluded(self, tag) -> bool:
        """Verifica se o tag deve ser excluído (menu, ad, etc)."""
        tag_class = " ".join(tag.get("class", []))
        tag_id = tag.get("id", "")
        combined = f"{tag_class} {tag_id}"
        return bool(self._EXCLUDE_PATTERNS.search(combined))
