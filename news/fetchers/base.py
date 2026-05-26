# -*- coding: utf-8 -*-
"""Classe base para fetchers."""

from abc import ABC, abstractmethod
from ..models import Source, FetchResult


class BaseFetcher(ABC):
    """Interface comum para todos os fetchers de notícias."""

    @abstractmethod
    def fetch(self, source: Source, limit: int = 15) -> FetchResult:
        """Busca notícias de uma fonte.
        
        Args:
            source: Fonte de notícias.
            limit: Número máximo de itens a retornar.
            
        Returns:
            FetchResult com itens encontrados.
        """
        ...
