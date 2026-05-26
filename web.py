# -*- coding: utf-8 -*-
"""Servidor web para a interface de notícias."""

import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from flask import Flask, jsonify, request
from datetime import datetime

from news.registry import SourceRegistry
from news.fetchers.rss_fetcher import RSSFetcher
from news.fetchers.scraper_fetcher import ScraperFetcher
from news.fetchers.llm_fetcher import LLMFetcher
from news.translator import Translator
from news.classifier import Classifier
from news.models import Source, FetchResult

app = Flask(__name__)
registry = SourceRegistry()
translator = Translator()
classifier = Classifier()


def _get_fetcher(estrategia: str):
    if estrategia == "rss":
        return RSSFetcher()
    elif estrategia == "scraping":
        return ScraperFetcher()
    elif estrategia == "llm":
        return LLMFetcher()
    return ScraperFetcher()


def _fetch_with_fallback(source: Source, limit: int) -> FetchResult:
    strategies = [source.estrategia]
    if source.estrategia == "rss":
        strategies += ["scraping", "llm"]
    elif source.estrategia == "scraping":
        strategies += ["llm"]

    result = None
    for strategy in strategies:
        fetcher = _get_fetcher(strategy)
        result = fetcher.fetch(source, limit)
        if result.sucesso:
            return result
    return result


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/fontes")
def api_fontes():
    """Retorna lista de fontes, opcionalmente filtrada."""
    pais = request.args.get("pais", "")
    estrategia = request.args.get("estrategia", "")

    sources = registry.all
    if pais:
        sources = [s for s in sources if pais.lower() in s.pais.lower()]
    if estrategia:
        sources = [s for s in sources if s.estrategia == estrategia]

    return jsonify([{
        "nome": s.nome,
        "pais": s.pais,
        "afiliacao": s.afiliacao,
        "url": s.url,
        "idioma": s.idioma,
        "estrategia": s.estrategia,
    } for s in sources])


@app.route("/api/paises")
def api_paises():
    """Retorna lista de países únicos."""
    return jsonify(registry.paises())


@app.route("/api/buscar")
def api_buscar():
    """Busca notícias de uma fonte."""
    termo = request.args.get("fonte", "")
    modo = request.args.get("modo", "manchetes")
    limite = int(request.args.get("limite", "15"))
    original = request.args.get("original", "false") == "true"

    if not termo:
        return jsonify({"erro": "Parâmetro 'fonte' é obrigatório."}), 400

    sources = registry.buscar(termo)
    if not sources:
        return jsonify({"erro": f"Fonte não encontrada: '{termo}'"}), 404

    source = sources[0]

    # Fetch
    result = _fetch_with_fallback(source, limite * 2)
    if not result or not result.sucesso:
        return jsonify({
            "fonte": source.nome,
            "pais": source.pais,
            "afiliacao": source.afiliacao,
            "estrategia": result.estrategia_usada if result else "?",
            "erro": result.erro if result else "Falha total",
            "itens": [],
        })

    # Translate
    if not original:
        translator.traduzir(result.itens, source.idioma)

    # Classify
    classified = classifier.classificar(
        result.itens, modo,
        source_name=source.nome,
        source_country=source.pais,
        limite=limite,
    )

    # Build response
    if modo == "resumo" and isinstance(classified, str):
        return jsonify({
            "fonte": source.nome,
            "pais": source.pais,
            "afiliacao": source.afiliacao,
            "estrategia": result.estrategia_usada,
            "modo": modo,
            "resumo": classified,
            "itens": [],
        })

    itens_json = []
    for item in classified:
        itens_json.append({
            "titulo": item.titulo_pt or item.titulo if not original else item.titulo,
            "lead": item.lead_pt or item.lead if not original else item.lead,
            "link": item.link,
            "data": item.data.strftime("%d/%m/%Y %H:%M") if item.data else None,
            "fonte": item.fonte,
        })

    return jsonify({
        "fonte": source.nome,
        "pais": source.pais,
        "afiliacao": source.afiliacao,
        "estrategia": result.estrategia_usada,
        "modo": modo,
        "itens": itens_json,
    })


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_PAGE


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agregador de Noticias Globais</title>
    <meta name="description" content="Agregador de noticias de 97 veiculos de 40 paises, traduzidas para portugues">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0f1117;
            --bg-secondary: #1a1d27;
            --bg-card: #21242f;
            --bg-hover: #2a2e3b;
            --bg-glass: rgba(33, 36, 47, 0.85);
            --text-primary: #e8eaed;
            --text-secondary: #9aa0ab;
            --text-dim: #5f6673;
            --accent-blue: #4f8cff;
            --accent-green: #34d399;
            --accent-yellow: #fbbf24;
            --accent-purple: #a78bfa;
            --accent-red: #f87171;
            --border: #2a2e3b;
            --shadow: 0 8px 32px rgba(0,0,0,0.3);
            --radius: 12px;
            --radius-sm: 8px;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* ── Layout ─────────────────────────── */
        .app {
            display: grid;
            grid-template-columns: 320px 1fr;
            min-height: 100vh;
        }

        /* ── Sidebar ────────────────────────── */
        .sidebar {
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            height: 100vh;
            position: sticky;
            top: 0;
        }

        .sidebar-header {
            padding: 24px 20px 16px;
            border-bottom: 1px solid var(--border);
        }

        .sidebar-header h1 {
            font-size: 18px;
            font-weight: 700;
            color: var(--accent-blue);
            letter-spacing: -0.5px;
        }

        .sidebar-header p {
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 4px;
        }

        .search-box {
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
        }

        .search-box input {
            width: 100%;
            padding: 10px 14px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-box input:focus {
            border-color: var(--accent-blue);
        }

        .search-box input::placeholder {
            color: var(--text-dim);
        }

        .country-filter {
            padding: 8px 20px;
            border-bottom: 1px solid var(--border);
        }

        .country-filter select {
            width: 100%;
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
            outline: none;
            cursor: pointer;
        }

        .source-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px 12px;
        }

        .source-list::-webkit-scrollbar { width: 4px; }
        .source-list::-webkit-scrollbar-track { background: transparent; }
        .source-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

        .source-item {
            padding: 10px 12px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 2px;
        }

        .source-item:hover { background: var(--bg-hover); }
        .source-item.active { background: var(--accent-blue); color: white; }
        .source-item.active .source-meta { color: rgba(255,255,255,0.7); }
        .source-item.active .strategy-badge { background: rgba(255,255,255,0.2); color: white; }

        .source-info { flex: 1; min-width: 0; }

        .source-name {
            font-size: 13px;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .source-meta {
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 2px;
        }

        .strategy-badge {
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 10px;
            font-weight: 600;
            flex-shrink: 0;
        }

        .badge-rss { background: rgba(52,211,153,0.15); color: var(--accent-green); }
        .badge-scraping { background: rgba(251,191,36,0.15); color: var(--accent-yellow); }
        .badge-llm { background: rgba(167,139,250,0.15); color: var(--accent-purple); }

        /* ── Main Content ───────────────────── */
        .main {
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }

        .toolbar {
            padding: 16px 32px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 12px;
            background: var(--bg-glass);
            backdrop-filter: blur(12px);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .mode-tabs {
            display: flex;
            gap: 4px;
            background: var(--bg-primary);
            padding: 4px;
            border-radius: var(--radius-sm);
        }

        .mode-tab {
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
        }

        .mode-tab:hover { color: var(--text-primary); }

        .mode-tab.active {
            background: var(--accent-blue);
            color: white;
        }

        .toolbar-right {
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .limit-select {
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
            outline: none;
        }

        /* ── Content Area ───────────────────── */
        .content {
            flex: 1;
            padding: 32px;
            max-width: 900px;
        }

        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 60vh;
            text-align: center;
        }

        .welcome h2 {
            font-size: 28px;
            font-weight: 300;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .welcome p {
            color: var(--text-dim);
            font-size: 14px;
        }

        /* ── Loading ────────────────────────── */
        .loading {
            display: none;
            align-items: center;
            gap: 12px;
            padding: 40px 0;
        }

        .loading.visible { display: flex; }

        .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid var(--border);
            border-top-color: var(--accent-blue);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin { to { transform: rotate(360deg); } }

        .loading-text {
            color: var(--text-secondary);
            font-size: 14px;
        }

        /* ── Results Header ─────────────────── */
        .result-header {
            display: none;
            margin-bottom: 24px;
            padding: 20px 24px;
            background: var(--bg-card);
            border-radius: var(--radius);
            border: 1px solid var(--border);
        }

        .result-header.visible { display: block; }

        .result-header h2 {
            font-size: 20px;
            font-weight: 600;
        }

        .result-meta {
            display: flex;
            gap: 16px;
            margin-top: 6px;
            font-size: 13px;
            color: var(--text-secondary);
        }

        .result-meta span { display: flex; align-items: center; gap: 4px; }

        /* ── News Items ─────────────────────── */
        .news-list { display: flex; flex-direction: column; gap: 8px; }

        .news-item {
            padding: 18px 24px;
            background: var(--bg-card);
            border-radius: var(--radius);
            border: 1px solid var(--border);
            transition: all 0.2s;
            cursor: pointer;
            text-decoration: none;
            color: inherit;
            display: block;
        }

        .news-item:hover {
            border-color: var(--accent-blue);
            transform: translateY(-1px);
            box-shadow: var(--shadow);
        }

        .news-number {
            font-size: 12px;
            font-weight: 700;
            color: var(--accent-blue);
            margin-bottom: 6px;
        }

        .news-title {
            font-size: 15px;
            font-weight: 600;
            line-height: 1.4;
            margin-bottom: 6px;
        }

        .news-lead {
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
            margin-bottom: 8px;
        }

        .news-footer {
            font-size: 12px;
            color: var(--text-dim);
            display: flex;
            gap: 12px;
        }

        /* ── Resumo ─────────────────────────── */
        .resumo-card {
            padding: 24px 28px;
            background: linear-gradient(135deg, rgba(167,139,250,0.1) 0%, rgba(79,140,255,0.1) 100%);
            border: 1px solid rgba(167,139,250,0.3);
            border-radius: var(--radius);
            line-height: 1.7;
            font-size: 14px;
            white-space: pre-wrap;
        }

        /* ── Error ──────────────────────────── */
        .error-msg {
            padding: 16px 20px;
            background: rgba(248,113,113,0.1);
            border: 1px solid rgba(248,113,113,0.3);
            border-radius: var(--radius-sm);
            color: var(--accent-red);
            font-size: 14px;
        }

        /* ── Responsive ─────────────────────── */
        @media (max-width: 768px) {
            .app { grid-template-columns: 1fr; }
            .sidebar { height: auto; position: relative; max-height: 40vh; }
            .content { padding: 16px; }
        }
    </style>
</head>
<body>
    <div class="app">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="sidebar-header">
                <h1>Noticias Globais</h1>
                <p>97 veiculos &bull; 40 paises &bull; em portugues</p>
            </div>
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Buscar veiculo..." autocomplete="off">
            </div>
            <div class="country-filter">
                <select id="countryFilter">
                    <option value="">Todos os paises</option>
                </select>
            </div>
            <div class="source-list" id="sourceList"></div>
        </aside>

        <!-- Main -->
        <main class="main">
            <div class="toolbar">
                <div class="mode-tabs">
                    <button class="mode-tab active" data-mode="manchetes">Manchetes</button>
                    <button class="mode-tab" data-mode="recentes">Recentes</button>
                    <button class="mode-tab" data-mode="top">Destaques</button>
                    <button class="mode-tab" data-mode="resumo">Resumo IA</button>
                </div>
                <div class="toolbar-right">
                    <select class="limit-select" id="limitSelect">
                        <option value="5">5 noticias</option>
                        <option value="10">10 noticias</option>
                        <option value="15" selected>15 noticias</option>
                        <option value="25">25 noticias</option>
                    </select>
                </div>
            </div>

            <div class="content" id="content">
                <div class="welcome" id="welcome">
                    <h2>Selecione um veiculo</h2>
                    <p>Escolha uma fonte na barra lateral para ver as noticias de hoje</p>
                </div>

                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <span class="loading-text" id="loadingText">Buscando noticias...</span>
                </div>

                <div class="result-header" id="resultHeader">
                    <h2 id="resultTitle"></h2>
                    <div class="result-meta">
                        <span id="resultCountry"></span>
                        <span>&bull;</span>
                        <span id="resultAffiliation"></span>
                        <span>&bull;</span>
                        <span id="resultStrategy"></span>
                    </div>
                </div>

                <div class="news-list" id="newsList"></div>
            </div>
        </main>
    </div>

    <script>
        // ── State ────────────────────────────────────────────────────────────
        let allSources = [];
        let currentSource = null;
        let currentMode = "manchetes";

        const STRATEGY_LABELS = { rss: "RSS Feed", scraping: "Web Scraping", llm: "IA (Gemini)" };
        const STRATEGY_CLASS = { rss: "badge-rss", scraping: "badge-scraping", llm: "badge-llm" };

        // ── Init ─────────────────────────────────────────────────────────────
        async function init() {
            const [sources, countries] = await Promise.all([
                fetch("/api/fontes").then(r => r.json()),
                fetch("/api/paises").then(r => r.json()),
            ]);
            allSources = sources;

            // Populate country filter
            const sel = document.getElementById("countryFilter");
            countries.forEach(c => {
                const opt = document.createElement("option");
                opt.value = c;
                opt.textContent = c;
                sel.appendChild(opt);
            });

            renderSources(allSources);
            setupEventListeners();
        }

        // ── Render Sources ───────────────────────────────────────────────────
        function renderSources(sources) {
            const list = document.getElementById("sourceList");
            list.innerHTML = sources.map(s => `
                <div class="source-item${currentSource === s.nome ? ' active' : ''}" data-name="${s.nome}">
                    <div class="source-info">
                        <div class="source-name">${s.nome}</div>
                        <div class="source-meta">${s.pais} &bull; ${s.afiliacao.substring(0, 25)}</div>
                    </div>
                    <span class="strategy-badge ${STRATEGY_CLASS[s.estrategia] || ''}">${STRATEGY_LABELS[s.estrategia] || s.estrategia}</span>
                </div>
            `).join("");

            // Click handlers
            list.querySelectorAll(".source-item").forEach(item => {
                item.addEventListener("click", () => {
                    currentSource = item.dataset.name;
                    document.querySelectorAll(".source-item").forEach(i => i.classList.remove("active"));
                    item.classList.add("active");
                    fetchNews(currentSource);
                });
            });
        }

        // ── Fetch News ───────────────────────────────────────────────────────
        async function fetchNews(sourceName) {
            const limite = document.getElementById("limitSelect").value;
            showLoading(sourceName);

            try {
                const params = new URLSearchParams({
                    fonte: sourceName,
                    modo: currentMode,
                    limite: limite,
                });
                const resp = await fetch(`/api/buscar?${params}`);
                const data = await resp.json();
                hideLoading();

                if (data.erro && data.itens && data.itens.length === 0) {
                    showError(data.erro);
                    return;
                }

                showResults(data);
            } catch (err) {
                hideLoading();
                showError("Erro de conexao: " + err.message);
            }
        }

        // ── Show Results ─────────────────────────────────────────────────────
        function showResults(data) {
            // Header
            const header = document.getElementById("resultHeader");
            header.classList.add("visible");
            document.getElementById("resultTitle").textContent = data.fonte;
            document.getElementById("resultCountry").textContent = data.pais;
            document.getElementById("resultAffiliation").textContent = data.afiliacao;
            document.getElementById("resultStrategy").textContent = "via " + (STRATEGY_LABELS[data.estrategia] || data.estrategia);

            const list = document.getElementById("newsList");

            // Resumo mode
            if (data.resumo) {
                list.innerHTML = `<div class="resumo-card">${data.resumo}</div>`;
                return;
            }

            // News items
            if (!data.itens || data.itens.length === 0) {
                list.innerHTML = '<div class="error-msg">Nenhuma noticia encontrada.</div>';
                return;
            }

            list.innerHTML = data.itens.map((item, i) => {
                const link = item.link || "#";
                const target = item.link ? ' target="_blank" rel="noopener"' : '';
                return `
                    <a class="news-item" href="${link}"${target}>
                        <div class="news-number">${String(i + 1).padStart(2, '0')}</div>
                        <div class="news-title">${item.titulo}</div>
                        ${item.lead ? `<div class="news-lead">${item.lead.substring(0, 250)}</div>` : ''}
                        <div class="news-footer">
                            ${item.data ? `<span>${item.data}</span>` : ''}
                            ${item.link ? `<span>${new URL(item.link).hostname}</span>` : ''}
                        </div>
                    </a>
                `;
            }).join("");
        }

        // ── Loading / Error ──────────────────────────────────────────────────
        function showLoading(name) {
            document.getElementById("welcome").style.display = "none";
            document.getElementById("resultHeader").classList.remove("visible");
            document.getElementById("newsList").innerHTML = "";
            const loading = document.getElementById("loading");
            loading.classList.add("visible");
            document.getElementById("loadingText").textContent = `Buscando ${name}...`;
        }

        function hideLoading() {
            document.getElementById("loading").classList.remove("visible");
        }

        function showError(msg) {
            document.getElementById("newsList").innerHTML = `<div class="error-msg">${msg}</div>`;
        }

        // ── Event Listeners ──────────────────────────────────────────────────
        function setupEventListeners() {
            // Search
            document.getElementById("searchInput").addEventListener("input", (e) => {
                const q = e.target.value.toLowerCase();
                const filtered = allSources.filter(s =>
                    s.nome.toLowerCase().includes(q) || s.pais.toLowerCase().includes(q)
                );
                renderSources(filtered);
            });

            // Country filter
            document.getElementById("countryFilter").addEventListener("change", (e) => {
                const country = e.target.value;
                const filtered = country
                    ? allSources.filter(s => s.pais === country)
                    : allSources;
                renderSources(filtered);
            });

            // Mode tabs
            document.querySelectorAll(".mode-tab").forEach(tab => {
                tab.addEventListener("click", () => {
                    document.querySelectorAll(".mode-tab").forEach(t => t.classList.remove("active"));
                    tab.classList.add("active");
                    currentMode = tab.dataset.mode;
                    if (currentSource) fetchNews(currentSource);
                });
            });

            // Limit change
            document.getElementById("limitSelect").addEventListener("change", () => {
                if (currentSource) fetchNews(currentSource);
            });
        }

        init();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    print("\n  Abrindo em: http://localhost:5000\n")
    app.run(debug=False, port=5000)
