# 🗞️ Agregador de Notícias Global

Uma ferramenta completa em Python para agregar, traduzir e classificar notícias de **97 fontes globais** de informação. O projeto conta com uma interface de linha de comando (CLI) rica e uma interface Web moderna, responsiva e otimizada (Dark Mode) baseada em Flask.

Todas as notícias são traduzidas em tempo real para o **Português Brasileiro** através da API do Gemini (suportando a família de modelos Gemini 3.5, 3.1, 2.5, 2.0 e 1.5).

---

## ✨ Funcionalidades Principais

* **Cobertura Ampla**: Cobertura de 97 principais veículos jornalísticos do mundo (América do Norte, Europa, Ásia, América Latina, África e Oceania).
* **Tradução Automática Inteligente**: Traduz títulos e leads em lote para o Português Brasileiro (com tom jornalístico), pulando a tradução caso a fonte já seja em português.
* **Busca Accent-Insensitive**: A busca e seleção de fontes são tolerantes a acentos e variações ortográficas (ex: buscar por `"El Pais"` localiza a fonte `"El País"`).
* **Tratamento Multicanal de Captura**:
  1. **RSS Reader**: Busca rápida e estruturada de feeds RSS/Atom.
  2. **Scraper Genérico por Heurísticas**: Extração inteligente da estrutura de homepages usando heurísticas avançadas de tags e classes HTML para fontes sem RSS.
  3. **LLM Fallback**: Extração via Gemini para portais que utilizam sistemas anti-bot avançados ou estruturas de página exóticas.
* **Ações Individuais em Notícias**:
  * **"Ler no Site"**: Abre diretamente a matéria de interesse no veículo jornalístico original.
  * **"Resumir com IA"**: Realiza o scraping dinâmico do conteúdo integral do artigo (limpando paywalls e anúncios) ou usa metadados para produzir um resumo customizado em português brasileiro.
* **Gerenciador Dinâmico de API Keys & Modelos**:
  * Painel de controle no aplicativo para cadastrar, listar (com máscara), testar validade e ativar múltiplas chaves API do Gemini.
  * Seleção dinâmica entre múltiplos modelos do Gemini (3.5 Flash, 3.1 Pro Preview, 3 Flash Preview, 3.1 Flash-Lite, 2.5 Flash/Pro, 2.0 Flash e gerações anteriores 1.5).
* **4 Modos de Classificação**:
  * `manchetes`: A ordem exata de destaque da capa editorial do veículo.
  * `recentes`: Organização cronológica descendente baseada no timestamp de publicação.
  * `top`: Score heurístico combinando posição de capa, presença de lead e riqueza de conteúdo.
  * `resumo`: Resumo executivo em 5 pontos elaborado por Inteligência Artificial (Gemini) a partir de todas as manchetes disponíveis.

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem**: Python 3.10+
* **Interface Web**: Flask (HTML5, Vanilla CSS, Modern JS, Dark Theme nativo)
* **Interface CLI**: `rich` (Saída colorida e tabelas formatadas)
* **Parsing & Scraping**: `feedparser`, `beautifulsoup4`, `lxml`, `requests`
* **Inteligência Artificial**: `google-genai` (suportando a família Gemini 3.5, 3.1, 3.0, 2.5, 2.0 e 1.5)
* **Gerenciamento de Ambiente e Configuração**: `python-dotenv` e armazenamento dinâmico local (`api_keys.json`)

---

## 🚀 Instalação e Configuração

### 1. Clonar o Repositório e Acessar o Diretório
```bash
git clone <URL_DO_SEU_REPOSITORIO>
cd NEWS
```

### 2. Instalar as Dependências
Instale todos os pacotes necessários especificados no arquivo `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 3. Configurar as Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto (este arquivo é automaticamente ignorado pelo Git para segurança de suas credenciais) e adicione sua chave de acesso à API do Gemini:
```env
GEMINI_API_KEY=Sua_Chave_De_API_Gemini_Aqui
```

---

## 💻 Como Utilizar a Interface CLI

O projeto é empacotado como um módulo executável do Python. Você pode usá-lo chamando `python -m news`.

### Exemplos de Uso

* **Listar fontes disponíveis**:
  ```bash
  python -m news listar
  ```

* **Listar fontes filtradas por país**:
  ```bash
  python -m news listar --pais Brasil
  ```

* **Buscar manchetes de um veículo específico (traduzidas por padrão)**:
  ```bash
  python -m news buscar "Folha de S.Paulo"
  ```

* **Buscar notícias no idioma original (sem tradução)**:
  ```bash
  python -m news buscar "The New York Times" --original
  ```

* **Escolher um modo de classificação específico**:
  ```bash
  python -m news buscar "The Guardian" --modo resumo
  python -m news buscar "Le Monde" --modo top --limite 5
  ```

* **Buscar notícias de todas as fontes de um país de uma vez**:
  ```bash
  python -m news buscar --pais Portugal --modo recentes
  ```

---

## 🌐 Como Utilizar a Interface Web (Flask)

A interface Web fornece um dashboard completo onde você pode navegar pelos países, buscar fontes pelo nome, alternar os modos de classificação e ler as notícias agregadas instantaneamente em um layout em grade responsivo com Dark Mode nativo.

### Iniciar o Servidor Web
```bash
python web.py
```

Por padrão, o servidor estará rodando em:  
👉 **`http://localhost:5000`**

### Recursos da Interface Web:
* **Barra Lateral Interativa**: Filtro de veículos por busca textual rápida e seleção direta de países.
* **Seletor de Modos**: Abas superiores rápidas para mudar dinamicamente entre Manchetes, Recentes, Top e Resumo Inteligente.
* **Grade de Cards**: Visualização limpa dos artigos, com títulos em destaque, leads explicativos, tags de país/idioma e links diretos para a fonte original.
* **Resumos On-Demand**: Botão "Resumir com IA" para gerar na hora o resumo de qualquer matéria de interesse, buscando o texto integral do artigo sempre que possível.
* **Configurações Rápidas ("Chaves & Modelos")**: Modal no canto inferior esquerdo para testar, gerenciar e ativar chaves de API e alternar entre modelos do Gemini dinamicamente de forma síncrona.
* **Resiliência e Mensagens Claras**: Lógica de auto-retry com backoff exponencial contra limites de taxa (HTTP 429) e interceptação de chaves inválidas fornecendo instruções de correção na UI.

---

## 📂 Estrutura de Arquivos

```
NEWS/
├── news/                              # Módulo Python Principal
│   ├── fetchers/                      # Sistemas de Coleta de Notícias
│   │   ├── base.py                    # Classe Abstrata de Fetching
│   │   ├── rss_fetcher.py             # Parser de RSS (feedparser)
│   │   ├── scraper_fetcher.py         # Extrator de HTML (BeautifulSoup)
│   │   └── llm_fetcher.py             # Extrator Baseado em IA (Gemini)
│   ├── classifier.py                  # Classificador dos 4 Modos
│   ├── cli.py                         # CLI Parser
│   ├── config.py                      # Carregamento de Env e API Keys
│   ├── display.py                     # Renderização Rich no Terminal
│   ├── models.py                      # Modelagem de Dados (Dataclasses)
│   ├── registry.py                    # Gerenciador de Fontes e CSV
│   ├── translator.py                  # Tradutor Inteligente
│   └── __main__.py                    # Ponto de Entrada do Módulo
├── Principais noticiarios...csv       # Lista Base de 97 Veículos Globais
├── sources_config.json                # Configurações de Estratégias por Veículo
├── requirements.txt                   # Dependências do Projeto
├── web.py                             # Servidor Flask Web
├── .gitignore                         # Arquivos ignorados pelo Git
└── README.md                          # Instruções do Projeto (Este arquivo)
```
