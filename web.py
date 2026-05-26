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

import json
from pathlib import Path

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

API_KEYS_FILE = Path(__file__).parent / "api_keys.json"


def _load_api_keys():
    if API_KEYS_FILE.exists():
        return json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
    return {"keys": [], "active": ""}


def _save_api_keys(data):
    API_KEYS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _reload_modules_with_key(api_key: str):
    """Recarrega translator e classifier com a nova API key."""
    global translator, classifier
    translator.reload_key(api_key)
    # Classifier usa genai sob demanda, recarregar
    from google import genai
    classifier._gemini_client = genai.Client(api_key=api_key)


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


# ── API Keys Management ───────────────────────────────────────────────────────

@app.route("/api/keys", methods=["GET"])
def api_keys_list():
    """Retorna lista de API keys salvas (mascaradas)."""
    data = _load_api_keys()
    masked = []
    for entry in data.get("keys", []):
        key = entry.get("key", "")
        masked_key = key[:8] + "..." + key[-4:] if len(key) > 12 else "****"
        masked.append({
            "label": entry.get("label", ""),
            "key_masked": masked_key,
            "is_active": entry.get("label") == data.get("active", ""),
        })
    return jsonify({"keys": masked, "active": data.get("active", "")})


@app.route("/api/keys", methods=["POST"])
def api_keys_add():
    """Adiciona uma nova API key."""
    body = request.get_json()
    label = body.get("label", "").strip()
    key = body.get("key", "").strip()
    if not label or not key:
        return jsonify({"erro": "Label e key são obrigatórios."}), 400

    data = _load_api_keys()
    # Verificar duplicata
    for entry in data["keys"]:
        if entry["label"] == label:
            return jsonify({"erro": f"Já existe uma key com o label '{label}'."}), 409

    data["keys"].append({"label": label, "key": key})
    # Se é a primeira, ativar automaticamente
    if not data["active"]:
        data["active"] = label
        _reload_modules_with_key(key)
    _save_api_keys(data)
    return jsonify({"ok": True, "mensagem": f"Key '{label}' adicionada."})


@app.route("/api/keys/<label>", methods=["DELETE"])
def api_keys_delete(label):
    """Remove uma API key."""
    data = _load_api_keys()
    data["keys"] = [e for e in data["keys"] if e["label"] != label]
    if data["active"] == label:
        data["active"] = data["keys"][0]["label"] if data["keys"] else ""
        if data["active"]:
            for e in data["keys"]:
                if e["label"] == data["active"]:
                    _reload_modules_with_key(e["key"])
                    break
    _save_api_keys(data)
    return jsonify({"ok": True})


@app.route("/api/keys/activate", methods=["POST"])
def api_keys_activate():
    """Define uma API key como ativa."""
    body = request.get_json()
    label = body.get("label", "").strip()
    data = _load_api_keys()
    found = None
    for entry in data["keys"]:
        if entry["label"] == label:
            found = entry
            break
    if not found:
        return jsonify({"erro": f"Key '{label}' não encontrada."}), 404

    data["active"] = label
    _save_api_keys(data)
    _reload_modules_with_key(found["key"])
    return jsonify({"ok": True, "mensagem": f"Key '{label}' ativada."})


@app.route("/api/keys/test", methods=["POST"])
def api_keys_test():
    """Testa se uma API key é válida."""
    body = request.get_json()
    key = body.get("key", "").strip()
    if not key:
        return jsonify({"erro": "Key é obrigatória."}), 400
    try:
        from google import genai
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(model="gemini-2.5-flash", contents="Diga apenas: OK")
        return jsonify({"ok": True, "mensagem": "Key válida!", "resposta": resp.text.strip()[:50]})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)[:200]})


@app.route("/api/model", methods=["GET"])
def api_get_model():
    """Retorna o modelo Gemini ativo configurado."""
    data = _load_api_keys()
    active_model = data.get("active_model", "gemini-2.5-flash")
    return jsonify({"active_model": active_model})


@app.route("/api/model", methods=["POST"])
def api_post_model():
    """Salva a escolha do modelo Gemini ativo."""
    body = request.get_json() or {}
    model = body.get("model", "").strip()
    if not model:
        return jsonify({"erro": "Parâmetro 'model' é obrigatório."}), 400

    data = _load_api_keys()
    data["active_model"] = model
    _save_api_keys(data)
    return jsonify({"ok": True, "mensagem": f"Modelo ativo alterado para '{model}' com sucesso."})


@app.route("/api/resumir-artigo", methods=["POST"])
def api_resumir_artigo():
    """Gera um resumo da matéria (via URL ou dados de título/lead) via Gemini."""
    body = request.get_json() or {}
    url = body.get("url", "").strip()
    titulo = body.get("titulo", "").strip()
    lead = body.get("lead", "").strip()

    if not url and not titulo:
        return jsonify({"erro": "Parâmetro 'url' ou 'titulo' é obrigatório."}), 400

    # 1. Carregar a API key ativa
    data_keys = _load_api_keys()
    key = data_keys.get("active", "")
    from news.config import GEMINI_API_KEY, get_active_model, is_invalid_key_error
    active_key = None
    if key:
        for entry in data_keys.get("keys", []):
            if entry.get("label") == key:
                active_key = entry.get("key", "")
                break
    api_key_to_use = active_key or GEMINI_API_KEY

    if not api_key_to_use:
        return jsonify({"erro": "Nenhuma Gemini API Key configurada. Salve uma chave nas configurações."}), 400

    # 2. Tentar extrair o conteúdo do artigo se a URL estiver disponível
    artigo_texto = ""
    if url and url != "#":
        try:
            import requests
            from bs4 import BeautifulSoup
            from news.config import HTTP_HEADERS, HTTP_TIMEOUT

            resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                paragraphs = soup.find_all("p")
                text_blocks = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text) > 40 and not any(x in text.lower() for x in ["cookies", "política", "termos de uso", "inscreva-se", "newsletter", "todos os direitos"]):
                        text_blocks.append(text)
                artigo_texto = "\n\n".join(text_blocks[:15])
        except Exception as e:
            print(f"[Artigo] Erro ao extrair texto do link {url}: {e}")

    # 3. Construir o prompt para o Gemini
    if artigo_texto and len(artigo_texto) > 300:
        prompt = f"""Você é um assistente de jornalismo altamente qualificado. 
Escreva um resumo conciso, envolvente e informativo de 2 a 3 parágrafos do artigo abaixo. 
O resumo deve estar inteiramente em português brasileiro, mantendo um tom neutro e jornalístico. 
Não invente fatos adicionais e não inclua saudações ou metadados de sistema.

CONTEÚDO DO ARTIGO:
Título original: {titulo}
Link original: {url}

{artigo_texto}
"""
    else:
        prompt = f"""Você é um assistente de jornalismo. 
Com base no título e descrição preliminar de uma notícia, escreva um parágrafo de resumo explicativo em português brasileiro.
Mantenha um tom profissional e jornalístico. Se a notícia original for em outro idioma, traduza os conceitos com precisão.

DADOS DA NOTÍCIA:
Título: {titulo}
Descrição/Lead: {lead}
Link: {url}
"""

    # 4. Chamar o Gemini
    try:
        from google import genai
        client = genai.Client(api_key=api_key_to_use)
        
        last_error = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=get_active_model(),
                    contents=prompt,
                )
                return jsonify({
                    "sucesso": True,
                    "resumo": response.text.strip(),
                    "usou_artigo_completo": bool(artigo_texto and len(artigo_texto) > 300)
                })
            except Exception as ex:
                last_error = ex
                if is_invalid_key_error(ex):
                    return jsonify({"erro": "A chave API do Gemini ativa no momento é inválida ou expirou. Por favor, acesse o menu 'Chaves & Modelos' e ative uma chave válida."}), 400
                elif "429" in str(ex) or "RESOURCE_EXHAUSTED" in str(ex):
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
                else:
                    break
        if is_invalid_key_error(last_error):
            return jsonify({"erro": "A chave API do Gemini ativa no momento é inválida ou expirou. Por favor, acesse o menu 'Chaves & Modelos' e ative uma chave válida."}), 400
        return jsonify({"erro": f"Erro na chamada do Gemini: {last_error}"}), 500

    except Exception as e:
        if is_invalid_key_error(e):
            return jsonify({"erro": "A chave API do Gemini ativa no momento é inválida ou expirou. Por favor, acesse o menu 'Chaves & Modelos' e ative uma chave válida."}), 400
        return jsonify({"erro": f"Erro interno ao gerar o resumo: {e}"}), 500


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
            color: inherit;
            display: block;
        }

        .news-item:hover {
            border-color: var(--border);
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
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            margin-top: 12px;
        }

        .news-footer-left {
            display: flex;
            gap: 12px;
            font-size: 12px;
            color: var(--text-dim);
        }

        .news-footer-right {
            display: flex;
            gap: 8px;
        }

        .card-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            font-family: inherit;
            border: 1px solid var(--border);
        }

        .card-btn-link {
            background: transparent;
            color: var(--text-secondary);
        }

        .card-btn-link:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
            border-color: var(--text-dim);
        }

        .card-btn-ai {
            background: linear-gradient(135deg, var(--accent-purple) 0%, var(--accent-blue) 100%);
            color: white;
            border: none;
        }

        .card-btn-ai:hover {
            opacity: 0.9;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(167, 139, 250, 0.3);
        }

        /* ── News Summary Box ────────────────── */
        .news-summary-box {
            display: none;
            margin-top: 14px;
            padding: 16px 20px;
            background: rgba(167, 139, 250, 0.05);
            border-left: 3px solid var(--accent-purple);
            border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
            font-size: 13px;
            line-height: 1.6;
            color: var(--text-primary);
            animation: fadeIn 0.3s ease-out;
        }

        .news-summary-box.visible {
            display: block;
        }

        .news-summary-box .spinner-sm {
            width: 16px;
            height: 16px;
            border: 2px solid var(--border);
            border-top-color: var(--accent-purple);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            display: inline-block;
            vertical-align: middle;
            margin-right: 8px;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
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

        /* ── Settings Button ────────────────── */
        .settings-btn {
            width: 100%;
            padding: 12px 16px;
            border: none;
            border-top: 1px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            font-family: inherit;
            font-size: 13px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.15s;
        }
        .settings-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
        .settings-icon { font-size: 16px; }

        /* ── Modal ──────────────────────────── */
        .modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(4px);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.visible { display: flex; }

        .modal {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            width: 520px;
            max-width: 95vw;
            max-height: 85vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }

        .modal-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .modal-header h3 { font-size: 16px; font-weight: 600; }
        .modal-close {
            background: none; border: none; color: var(--text-dim);
            font-size: 20px; cursor: pointer; padding: 4px;
        }
        .modal-close:hover { color: var(--text-primary); }

        .modal-body { padding: 20px 24px; }

        .key-form { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
        .key-form-row { display: flex; gap: 8px; }
        .key-form input {
            flex: 1; padding: 10px 14px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: inherit; font-size: 13px; outline: none;
        }
        .key-form input:focus { border-color: var(--accent-blue); }
        .key-form input::placeholder { color: var(--text-dim); }

        .btn {
            padding: 10px 18px;
            border-radius: var(--radius-sm);
            border: none;
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
            flex-shrink: 0;
        }
        .btn-primary { background: var(--accent-blue); color: white; }
        .btn-primary:hover { filter: brightness(1.1); }
        .btn-outline {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
        }
        .btn-outline:hover { border-color: var(--accent-blue); color: var(--text-primary); }
        .btn-danger { background: rgba(248,113,113,0.15); color: var(--accent-red); }
        .btn-danger:hover { background: rgba(248,113,113,0.25); }
        .btn-success { background: rgba(52,211,153,0.15); color: var(--accent-green); }

        .key-list { display: flex; flex-direction: column; gap: 6px; }
        .key-entry {
            display: flex; align-items: center; gap: 10px;
            padding: 12px 14px;
            background: var(--bg-primary);
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
        }
        .key-entry.active { border-color: var(--accent-green); }
        .key-label { font-weight: 500; font-size: 13px; }
        .key-masked { font-size: 12px; color: var(--text-dim); font-family: monospace; }
        .key-actions { margin-left: auto; display: flex; gap: 6px; }
        .key-active-badge {
            font-size: 10px; padding: 2px 8px;
            border-radius: 10px; font-weight: 600;
            background: rgba(52,211,153,0.15); color: var(--accent-green);
        }
        .key-status { font-size: 12px; margin-top: 8px; padding: 8px 12px; border-radius: var(--radius-sm); }
        .key-status.success { background: rgba(52,211,153,0.1); color: var(--accent-green); }
        .key-status.error { background: rgba(248,113,113,0.1); color: var(--accent-red); }
        .key-status.info { background: rgba(79,140,255,0.1); color: var(--accent-blue); }

        .key-section-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
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
            <button class="settings-btn" onclick="openSettings()">
                <span class="settings-icon">&#9881;</span> Chaves & Modelos
            </button>
        </aside>

        <!-- Settings Modal -->
        <div class="modal-overlay" id="settingsModal">
            <div class="modal">
                <div class="modal-header">
                    <h3>&#9881; Configurações do App</h3>
                    <button class="modal-close" onclick="closeSettings()">&times;</button>
                </div>
                <div class="modal-body">
                    <!-- Gemini API Key Section -->
                    <div class="key-section-title">Adicionar nova chave do Gemini</div>
                    <div class="key-form">
                        <div class="key-form-row">
                            <input type="text" id="keyLabel" placeholder="Nome (ex: Pessoal, Trabalho)" style="max-width:160px">
                            <input type="text" id="keyValue" placeholder="Cole a API Key aqui...">
                        </div>
                        <div class="key-form-row">
                            <button class="btn btn-outline" onclick="testKey()">Testar</button>
                            <button class="btn btn-primary" onclick="addKey()">Salvar</button>
                        </div>
                        <div class="key-status" id="keyStatus" style="display:none"></div>
                    </div>
                    <div class="key-section-title">Chaves salvas</div>
                    <div class="key-list" id="keyList" style="margin-bottom:24px">
                        <div style="color:var(--text-dim);font-size:13px;padding:8px 0">Nenhuma chave salva ainda.</div>
                    </div>

                    <!-- Gemini Model Section -->
                    <div class="key-section-title" style="margin-top:24px;border-top:1px solid var(--border);padding-top:16px">Modelo Gemini Ativo</div>
                    <div class="key-form" style="margin-bottom:12px">
                        <div class="key-form-row">
                            <select id="modelSelect" onchange="changeActiveModel()" class="limit-select" style="width:100%; padding:10px 14px; background:var(--bg-primary); border-radius:var(--radius-sm); border:1px solid var(--border); color:var(--text-primary); outline:none; font-size:13px; cursor:pointer;">
                                <option value="gemini-3.5-flash">Gemini 3.5 Flash (Estável)</option>
                                <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro (Preview)</option>
                                <option value="gemini-3-flash-preview">Gemini 3 Flash (Preview)</option>
                                <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash-Lite (Estável)</option>
                                <option value="gemini-3.1-flash-lite-preview">Gemini 3.1 Flash-Lite (Preview)</option>
                                <option value="gemini-3.1-flash-live-preview">Gemini 3.1 Flash Live (Preview)</option>
                                <option value="gemini-3.1-flash-tts-preview">Gemini 3.1 Flash TTS (Preview)</option>
                                <option value="gemini-2.5-flash">Gemini 2.5 Flash (Estável)</option>
                                <option value="gemini-2.5-pro">Gemini 2.5 Pro (Estável)</option>
                                <option value="gemini-2.0-flash">Gemini 2.0 Flash (Estável)</option>
                                <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
                                <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                            </select>
                        </div>
                        <div class="key-status" id="modelStatus" style="display:none"></div>
                    </div>
                </div>
            </div>
        </div>

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
                const hasLink = item.link && item.link !== "#";
                let hostname = "";
                if (hasLink) {
                    try {
                        hostname = new URL(item.link).hostname;
                    } catch (e) {
                        hostname = "link";
                    }
                }
                const encUrl = encodeURIComponent(item.link || "");
                const encTitulo = encodeURIComponent(item.titulo || "");
                const encLead = encodeURIComponent(item.lead || "");

                return `
                    <div class="news-item" id="news-item-${i}">
                        <div class="news-number">${String(i + 1).padStart(2, '0')}</div>
                        <div class="news-title">${item.titulo}</div>
                        ${item.lead ? `<div class="news-lead">${item.lead}</div>` : ''}
                        <div class="news-footer">
                            <div class="news-footer-left">
                                ${item.data ? `<span>${item.data}</span>` : ''}
                                ${hasLink ? `<span>${hostname}</span>` : ''}
                            </div>
                            <div class="news-footer-right">
                                ${hasLink ? `<a class="card-btn card-btn-link" href="${item.link}" target="_blank" rel="noopener">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:2px"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                                    Ler no Site
                                </a>` : ''}
                                <button class="card-btn card-btn-ai" onclick="toggleSummary(${i}, '${encUrl}', '${encTitulo}', '${encLead}')">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:2px"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                                    Resumir com IA
                                </button>
                            </div>
                        </div>
                        <div class="news-summary-box" id="summary-box-${i}"></div>
                    </div>
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

        // ── Settings / API Keys ──────────────────────────────────────────────
        function openSettings() {
            document.getElementById('settingsModal').classList.add('visible');
            loadKeys();
            loadActiveModel();
        }

        function closeSettings() {
            document.getElementById('settingsModal').classList.remove('visible');
        }

        // Fechar modal ao clicar fora
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) closeSettings();
        });

        async function loadKeys() {
            try {
                const resp = await fetch('/api/keys');
                const data = await resp.json();
                renderKeys(data);
            } catch (e) {
                console.error('Erro ao carregar keys:', e);
            }
        }

        function renderKeys(data) {
            const list = document.getElementById('keyList');
            if (!data.keys || data.keys.length === 0) {
                list.innerHTML = '<div style="color:var(--text-dim);font-size:13px;padding:8px 0">Nenhuma chave salva ainda.</div>';
                return;
            }
            list.innerHTML = data.keys.map(k => `
                <div class="key-entry${k.is_active ? ' active' : ''}">
                    <div>
                        <div class="key-label">${k.label}</div>
                        <div class="key-masked">${k.key_masked}</div>
                    </div>
                    ${k.is_active ? '<span class="key-active-badge">Ativa</span>' : ''}
                    <div class="key-actions">
                        ${!k.is_active ? `<button class="btn btn-success" onclick="activateKey('${k.label}')" style="padding:6px 12px;font-size:12px">Ativar</button>` : ''}
                        <button class="btn btn-danger" onclick="deleteKey('${k.label}')" style="padding:6px 12px;font-size:12px">Remover</button>
                    </div>
                </div>
            `).join('');
        }

        function showKeyStatus(msg, type) {
            const el = document.getElementById('keyStatus');
            el.textContent = msg;
            el.className = 'key-status ' + type;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 5000);
        }

        async function testKey() {
            const key = document.getElementById('keyValue').value.trim();
            if (!key) { showKeyStatus('Cole uma API key primeiro.', 'error'); return; }
            showKeyStatus('Testando...', 'info');
            try {
                const resp = await fetch('/api/keys/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key }),
                });
                const data = await resp.json();
                if (data.ok) {
                    showKeyStatus('Key valida! Resposta: ' + data.resposta, 'success');
                } else {
                    showKeyStatus('Key invalida: ' + data.erro, 'error');
                }
            } catch (e) {
                showKeyStatus('Erro ao testar: ' + e.message, 'error');
            }
        }

        async function addKey() {
            const label = document.getElementById('keyLabel').value.trim();
            const key = document.getElementById('keyValue').value.trim();
            if (!label || !key) { showKeyStatus('Preencha o nome e a key.', 'error'); return; }
            try {
                const resp = await fetch('/api/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label, key }),
                });
                const data = await resp.json();
                if (data.erro) { showKeyStatus(data.erro, 'error'); return; }
                showKeyStatus(data.mensagem, 'success');
                document.getElementById('keyLabel').value = '';
                document.getElementById('keyValue').value = '';
                loadKeys();
            } catch (e) {
                showKeyStatus('Erro: ' + e.message, 'error');
            }
        }

        async function activateKey(label) {
            try {
                const resp = await fetch('/api/keys/activate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label }),
                });
                const data = await resp.json();
                if (data.erro) { showKeyStatus(data.erro, 'error'); return; }
                showKeyStatus('Key ativada: ' + label, 'success');
                loadKeys();
            } catch (e) {
                showKeyStatus('Erro: ' + e.message, 'error');
            }
        }

        async function deleteKey(label) {
            if (!confirm('Remover a key "' + label + '"?')) return;
            try {
                await fetch('/api/keys/' + encodeURIComponent(label), { method: 'DELETE' });
                loadKeys();
            } catch (e) {
                showKeyStatus('Erro: ' + e.message, 'error');
            }
        }

        async function loadActiveModel() {
            try {
                const resp = await fetch('/api/model');
                const data = await resp.json();
                if (data.active_model) {
                    document.getElementById('modelSelect').value = data.active_model;
                }
            } catch (e) {
                console.error('Erro ao carregar modelo ativo:', e);
            }
        }

        async function changeActiveModel() {
            const select = document.getElementById('modelSelect');
            const model = select.value;
            const statusEl = document.getElementById('modelStatus');
            
            statusEl.textContent = 'Atualizando modelo...';
            statusEl.className = 'key-status info';
            statusEl.style.display = 'block';
            
            try {
                const resp = await fetch('/api/model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model })
                });
                const data = await resp.json();
                if (data.ok) {
                    statusEl.textContent = data.mensagem;
                    statusEl.className = 'key-status success';
                } else {
                    statusEl.textContent = 'Erro: ' + data.erro;
                    statusEl.className = 'key-status error';
                }
            } catch (e) {
                statusEl.textContent = 'Erro ao salvar: ' + e.message;
                statusEl.className = 'key-status error';
            }
            setTimeout(() => { statusEl.style.display = 'none'; }, 4000);
        }

        const activeSummaries = {};

        async function toggleSummary(index, encodedUrl, encodedTitulo, encodedLead) {
            const box = document.getElementById(`summary-box-${index}`);
            if (!box) return;

            // Se já estiver visível, ocultar
            if (box.classList.contains("visible")) {
                box.classList.remove("visible");
                return;
            }

            // Se já tivermos o resumo carregado, apenas mostrar
            if (activeSummaries[index]) {
                box.innerHTML = activeSummaries[index];
                box.classList.add("visible");
                return;
            }

            // Caso contrário, carregar via API
            const url = decodeURIComponent(encodedUrl);
            const titulo = decodeURIComponent(encodedTitulo);
            const lead = decodeURIComponent(encodedLead);

            box.innerHTML = `<span class="spinner-sm"></span> Gerando resumo inteligente com IA...`;
            box.classList.add("visible");

            try {
                const resp = await fetch("/api/resumir-artigo", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url, titulo, lead }),
                });
                const data = await resp.json();

                if (data.erro) {
                    box.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Erro ao gerar resumo: ${data.erro}</div>`;
                    return;
                }

                // Renderizar com sucesso
                const originLabel = data.usou_artigo_completo 
                    ? `<div style="font-size:11px;color:var(--accent-green);margin-bottom:8px;font-weight:600;display:flex;align-items:center;gap:4px;">
                         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                         Resumo gerado com base no artigo completo original
                       </div>`
                    : `<div style="font-size:11px;color:var(--accent-yellow);margin-bottom:8px;font-weight:600;display:flex;align-items:center;gap:4px;">
                         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                         Resumo gerado com base nos metadados (título e lead)
                       </div>`;

                const formattedSummary = `
                    ${originLabel}
                    <div style="white-space: pre-wrap; margin-top:4px;">${data.resumo}</div>
                `;

                activeSummaries[index] = formattedSummary;
                box.innerHTML = formattedSummary;
            } catch (err) {
                box.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Erro ao comunicar com o servidor: ${err.message}</div>`;
            }
        }

        init();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    print("\n  Abrindo em: http://localhost:5000\n")
    app.run(debug=False, port=5000)
