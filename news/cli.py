# -*- coding: utf-8 -*-
"""Interface CLI principal da ferramenta de notícias."""

import argparse
import sys

from .registry import SourceRegistry
from .fetchers.rss_fetcher import RSSFetcher
from .fetchers.scraper_fetcher import ScraperFetcher
from .fetchers.llm_fetcher import LLMFetcher
from .translator import Translator
from .classifier import Classifier
from .display import (
    mostrar_noticias, mostrar_fontes, mostrar_erro, mostrar_info, console
)
from .config import DEFAULT_LIMIT, DEFAULT_MODE
from .models import Source, FetchResult


def _get_fetcher(estrategia: str):
    """Retorna o fetcher adequado para a estratégia."""
    if estrategia == "rss":
        return RSSFetcher()
    elif estrategia == "scraping":
        return ScraperFetcher()
    elif estrategia == "llm":
        return LLMFetcher()
    else:
        return ScraperFetcher()


def _fetch_with_fallback(source: Source, limit: int) -> FetchResult:
    """Tenta buscar com a estratégia principal, com fallback em cascata."""
    # Ordem de tentativa baseada na estratégia configurada
    strategies = [source.estrategia]
    
    # Adicionar fallbacks
    if source.estrategia == "rss":
        strategies += ["scraping", "llm"]
    elif source.estrategia == "scraping":
        strategies += ["llm"]
    # LLM já é o último recurso

    for strategy in strategies:
        fetcher = _get_fetcher(strategy)
        result = fetcher.fetch(source, limit)
        if result.sucesso:
            return result
        # Se falhou, tentar próxima estratégia
        mostrar_info(f"  Estratégia '{strategy}' falhou para {source.nome}, tentando próxima...")

    # Todas falharam
    return result  # Retorna o último resultado com erro


def cmd_listar(args):
    """Comando: listar fontes disponíveis."""
    registry = SourceRegistry()

    if args.pais:
        sources = registry.por_pais(args.pais)
        if not sources:
            # Tentar busca parcial
            sources = [s for s in registry.all if args.pais.lower() in s.pais.lower()]
        titulo = f"Fontes — {args.pais}"
    elif args.estrategia:
        sources = registry.por_estrategia(args.estrategia)
        titulo = f"Fontes via {args.estrategia.upper()}"
    else:
        sources = registry.all
        titulo = "Todas as Fontes"

    if not sources:
        mostrar_erro(f"Nenhuma fonte encontrada para '{args.pais or args.estrategia}'.")
        return

    mostrar_fontes(sources, titulo)


def cmd_buscar(args):
    """Comando: buscar notícias de uma ou mais fontes."""
    registry = SourceRegistry()
    translator = Translator()
    classifier = Classifier()

    # Determinar fontes
    sources = []
    if args.pais:
        sources = registry.por_pais(args.pais)
        if not sources:
            sources = [s for s in registry.all if args.pais.lower() in s.pais.lower()]
    elif args.fonte:
        for termo in args.fonte:
            found = registry.buscar(termo)
            if found:
                sources.extend(found)
            else:
                mostrar_erro(f"Fonte não encontrada: '{termo}'")
    else:
        mostrar_erro("Especifique uma fonte ou use --pais para buscar por país.")
        return

    if not sources:
        mostrar_erro("Nenhuma fonte encontrada.")
        return

    # Se encontrou múltiplas e o usuário especificou um termo exato
    if len(sources) > 5 and not args.pais:
        console.print(f"\n  [yellow]⚠ {len(sources)} fontes encontradas. Mostrando a primeira.[/yellow]")
        console.print(f"  [dim]Use --pais para buscar por país ou seja mais específico.[/dim]\n")
        sources = sources[:1]

    modo = args.modo or DEFAULT_MODE
    limite = args.limite or DEFAULT_LIMIT

    for source in sources:
        # 1. Buscar notícias (com fallback)
        with console.status(f"[bold]Buscando {source.nome}...[/bold]", spinner="dots"):
            result = _fetch_with_fallback(source, limite * 2)  # Buscar mais para classificar

        if not result.sucesso:
            mostrar_noticias(result, [], modo)
            continue

        # 2. Traduzir para português
        if not args.original:
            with console.status("[bold]Traduzindo para português...[/bold]", spinner="dots"):
                translator.traduzir(result.itens, source.idioma)

        # 3. Classificar
        classified = classifier.classificar(
            result.itens, modo,
            source_name=source.nome,
            source_country=source.pais,
            limite=limite,
        )

        # 4. Exibir
        mostrar_noticias(result, classified, modo, mostrar_original=args.original)


def main():
    """Ponto de entrada do CLI."""
    parser = argparse.ArgumentParser(
        prog="news",
        description="🗞️  Agregador de Notícias Globais — 97 veículos de 40 países",
    )
    subparsers = parser.add_subparsers(dest="comando", help="Comandos disponíveis")

    # ── Comando: listar ───────────────────────────────────────────────────────
    p_listar = subparsers.add_parser(
        "listar", help="Listar fontes de notícias disponíveis"
    )
    p_listar.add_argument("--pais", "-p", help="Filtrar por país")
    p_listar.add_argument(
        "--estrategia", "-e", 
        choices=["rss", "scraping", "llm"],
        help="Filtrar por estratégia de busca",
    )
    p_listar.set_defaults(func=cmd_listar)

    # ── Comando: buscar ───────────────────────────────────────────────────────
    p_buscar = subparsers.add_parser(
        "buscar", help="Buscar notícias de uma fonte"
    )
    p_buscar.add_argument(
        "fonte", nargs="*", 
        help="Nome (parcial) do veículo. Ex: 'folha', 'nyt', 'guardian'"
    )
    p_buscar.add_argument("--pais", "-p", help="Buscar todas as fontes de um país")
    p_buscar.add_argument(
        "--modo", "-m",
        choices=["manchetes", "recentes", "top", "resumo"],
        default=DEFAULT_MODE,
        help=f"Modo de classificação (padrão: {DEFAULT_MODE})",
    )
    p_buscar.add_argument(
        "--limite", "-l", type=int, default=DEFAULT_LIMIT,
        help=f"Número máximo de notícias (padrão: {DEFAULT_LIMIT})",
    )
    p_buscar.add_argument(
        "--original", "-o", action="store_true",
        help="Manter idioma original (não traduzir)",
    )
    p_buscar.set_defaults(func=cmd_buscar)

    # Parsear argumentos
    args = parser.parse_args()

    if not args.comando:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
