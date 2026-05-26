# -*- coding: utf-8 -*-
"""Display formatado para o terminal usando rich."""

import sys
import os
from datetime import datetime

# Forçar UTF-8 no Windows antes de qualquer output
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .models import Source, NewsItem, FetchResult

console = Console(force_terminal=True)

# Cores por modo
MODE_COLORS = {
    "manchetes": "bright_blue",
    "recentes": "bright_green",
    "top": "bright_yellow",
    "resumo": "bright_magenta",
}

MODE_LABELS = {
    "manchetes": "[MANCHETES]",
    "recentes": "[MAIS RECENTES]",
    "top": "[DESTAQUES]",
    "resumo": "[RESUMO INTELIGENTE]",
}

STRATEGY_LABELS = {
    "rss": "RSS Feed",
    "scraping": "Web Scraping",
    "llm": "IA (Gemini)",
}


def mostrar_noticias(result: FetchResult, itens: list[NewsItem] | str, 
                     modo: str = "manchetes", mostrar_original: bool = False):
    """Exibe as notícias no terminal com formatação rich."""
    source = result.fonte
    color = MODE_COLORS.get(modo, "white")
    mode_label = MODE_LABELS.get(modo, modo)
    strategy_label = STRATEGY_LABELS.get(result.estrategia_usada, result.estrategia_usada)

    # Cabeçalho
    header = Text()
    header.append(f"\n  {source.nome}", style=f"bold {color}")
    header.append(f"  •  {source.pais}", style="dim")
    header.append(f"  •  {source.afiliacao}", style="dim italic")
    header.append(f"\n  {mode_label}", style=color)
    header.append(f"  •  via {strategy_label}", style="dim")
    header.append(f"  •  {datetime.now().strftime('%d/%m/%Y %H:%M')}", style="dim")

    console.print(Panel(header, border_style=color, box=box.ROUNDED))

    if not result.sucesso:
        console.print(f"\n  [red]✗ Erro: {result.erro}[/red]\n")
        return

    # Modo resumo: texto direto
    if modo == "resumo" and isinstance(itens, str):
        console.print()
        console.print(Panel(
            itens,
            title="Resumo do Dia",
            border_style="magenta",
            padding=(1, 2),
        ))
        console.print()
        return

    # Modos lista: exibir itens
    if not itens:
        console.print("\n  [dim]Nenhuma notícia encontrada.[/dim]\n")
        return

    console.print()
    for i, item in enumerate(itens, 1):
        titulo = item.titulo_display if not mostrar_original else item.titulo
        lead = item.lead_display if not mostrar_original else item.lead

        # Número + Título
        console.print(f"  [bold {color}]{i:2d}.[/bold {color}] [bold]{titulo}[/bold]")

        # Lead (se disponível)
        if lead:
            console.print(f"      [dim]{lead[:200]}[/dim]")

        # Data + Link
        meta_parts = []
        if item.data:
            meta_parts.append(item.data.strftime("%d/%m %H:%M"))
        if item.link:
            # Truncar link longo
            link_display = item.link[:80] + ("..." if len(item.link) > 80 else "")
            meta_parts.append(f"[link={item.link}]{link_display}[/link]")
        
        if meta_parts:
            console.print(f"      [dim cyan]{'  •  '.join(meta_parts)}[/dim cyan]")

        console.print()  # Espaço entre itens


def mostrar_fontes(sources: list[Source], titulo: str = "Fontes Disponíveis"):
    """Exibe tabela de fontes disponíveis."""
    table = Table(
        title=f"\n{titulo}",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold bright_blue",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Veículo", style="bold")
    table.add_column("País")
    table.add_column("Afiliação", style="italic")
    table.add_column("Idioma")
    table.add_column("Estratégia", style="dim")

    strategy_style = {
        "rss": "[green]RSS[/green]",
        "scraping": "[yellow]Scraping[/yellow]",
        "llm": "[magenta]IA[/magenta]",
    }

    for i, src in enumerate(sources, 1):
        table.add_row(
            str(i),
            src.nome,
            src.pais,
            src.afiliacao[:30],
            src.idioma,
            strategy_style.get(src.estrategia, src.estrategia),
        )

    console.print(table)
    console.print(f"\n  [dim]Total: {len(sources)} veículos[/dim]\n")


def mostrar_erro(mensagem: str):
    """Exibe mensagem de erro."""
    console.print(f"\n  [red bold]✗ Erro:[/red bold] [red]{mensagem}[/red]\n")


def mostrar_info(mensagem: str):
    """Exibe mensagem informativa."""
    console.print(f"\n  [dim]{mensagem}[/dim]")
