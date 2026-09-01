# RPA Crawler

Sistema de coleta de dados web com processamento assíncrono: crawlers orquestrados por fila (RabbitMQ), persistência em PostgreSQL e API REST (FastAPI). Implementação do [teste técnico](docs/DESAFIO.md) para Desenvolvedor Senior RPA.

## Arquitetura

```
┌─────────────┐  publica   ┌─────────────┐  consome   ┌─────────────┐
│   FastAPI   │───────────▶│  RabbitMQ   │───────────▶│   Worker    │
│    (api)    │            │   (queue)   │            │  (crawlers) │
└──────┬──────┘            └──────┬──────┘            └──────┬──────┘
       │                          │ DLX                      │
       │                   ┌──────▼──────┐            ┌──────▼──────┐
       │                   │     DLQ     │            │  Selenium   │
       │                   └─────────────┘            │ (chromium)  │
       │                                              └─────────────┘
       │                   ┌─────────────┐                   │
       └──────────────────▶│ PostgreSQL  │◀──────────────────┘
                           └─────────────┘
```

**Fluxo:** `POST /crawl/{source}` cria um registro de job (`pending`) no PostgreSQL, publica a mensagem `{job_id, source}` no RabbitMQ e responde `202` imediatamente. O worker consome a mensagem, marca o job como `running`, executa o(s) crawler(s), persiste os resultados e finaliza o job (`completed`/`failed`). O status e os dados ficam disponíveis via API.

### Estratégias de scraping (duas fontes, duas técnicas)

| Fonte | Técnica | Por quê |
|---|---|---|
| **Hockey Teams** (HTML paginado) | `httpx` + BeautifulSoup | Conteúdo estático: HTTP puro é mais rápido, estável e barato. O crawler descobre o total de páginas na paginação e percorre todas com retry/backoff. |
| **Oscar Films** (AJAX/JavaScript) | **Selenium** (Chromium headless via Remote WebDriver) | Conteúdo renderizado por JS: o crawler clica em cada ano, aguarda com condições explícitas (spinner oculto + staleness da tabela anterior + linhas presentes) e extrai o DOM renderizado. |

> **Trade-off registrado:** o endpoint AJAX do Oscar (`?ajax=true&year=YYYY`) retorna JSON puro e poderia ser consumido diretamente com `httpx`, o que seria mais eficiente e menos frágil. O Selenium foi usado deliberadamente porque o desafio pede duas estratégias distintas e automação de página dinâmica — exatamente o cenário em que browser automation se justifica.

### Decisões de projeto

- **Parsers puros**: recebem HTML e devolvem DTOs Pydantic, sem I/O — testáveis offline com fixtures reais dos sites. Linha malformada falha alto (`CrawlerError`) em vez de persistir dado incompleto.
- **API fina / worker separado**: a API nunca faz crawling; o worker (síncrono — Selenium e parsing são bloqueantes) roda na mesma imagem Docker com outro comando. Publisher assíncrono (`aio-pika`) na API; consumer síncrono (`pika`) no worker.
- **Resiliência na fila**: fila e mensagens duráveis, publisher confirms, `prefetch=1`, **ack manual só após commit**. Falha de crawl → retry limitado por contador de tentativas **persistido no banco** (sobrevive a crash do worker); esgotado o limite, a mensagem vai para a **DLQ** via dead-letter exchange e o job fica `failed` com o erro registrado.
- **Idempotência**: mensagem redelivered de job já `completed` é reconhecida e ignorada; reprocessamento substitui os resultados daquele job (delete+insert) — sem duplicatas.
- **`POST /crawl/all`**: cria **um** job que executa as duas coletas em sequência. Falha parcial → job `failed` indicando qual fonte falhou, mas os dados da fonte bem-sucedida permanecem gravados e consultáveis.
- **Resultados por job + snapshot**: cada linha coletada referencia o `job_id` (auditável, atende `GET /jobs/{id}/results`). `GET /results/{source}` responde o snapshot da **última coleta completa** da fonte, com filtros e paginação.
- **Graceful shutdown**: SIGTERM/SIGINT finaliza o job corrente, faz ack e fecha conexões; reconexão ao broker com backoff.
- **Desempenho**: as páginas do Hockey são buscadas concorrentemente (pool limitado por `HOCKEY_CONCURRENCY`, preservando a ordem); resultados entram no banco em lote (`executemany`); as consultas de listagem e de snapshot têm índices dedicados; a imagem Docker pré-compila bytecode. O CI exige cobertura mínima de 85% nos testes unitários.

## Como rodar

Pré-requisito: Docker + Docker Compose.

```bash
docker compose up --build -d
```

Sobe PostgreSQL, RabbitMQ, Selenium (chromium standalone), aplica as migrações (serviço one-shot) e inicia API e worker.

- **Dashboard web**: `http://localhost:8000` — agenda coletas, acompanha jobs em tempo real e explora os resultados com filtros.
- **Swagger UI**: `http://localhost:8000/docs` (ReDoc em `/redoc`).
- **RabbitMQ management**: `http://localhost:15672` (usuário/senha `rpa`/`rpa`).

Guia completo de operação — dashboard, exemplos de API, acesso ao banco e à fila — em **[docs/USAGE.md](docs/USAGE.md)**.

```bash
# agendar coletas
curl -X POST http://localhost:8000/crawl/hockey
curl -X POST http://localhost:8000/crawl/oscar
curl -X POST http://localhost:8000/crawl/all

# acompanhar
curl http://localhost:8000/jobs
curl http://localhost:8000/jobs/<job_id>
curl http://localhost:8000/jobs/<job_id>/results

# dados consolidados (última coleta completa)
curl "http://localhost:8000/results/hockey?year=1990&team=bruins"
curl "http://localhost:8000/results/oscar?year=2015"
```

### Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST | `/crawl/hockey` \| `/crawl/oscar` \| `/crawl/all` | Agenda a coleta e retorna `job_id` (202) |
| GET | `/jobs` | Lista jobs (filtros `status`, `source`; paginação `limit`/`offset`) |
| GET | `/jobs/{job_id}` | Status e detalhes do job (tentativas, erro, timestamps) |
| GET | `/jobs/{job_id}/results` | Dados coletados por aquele job |
| GET | `/results/hockey` | Snapshot da última coleta completa (filtros `year`, `team`) |
| GET | `/results/oscar` | Snapshot da última coleta completa (filtros `year`, `title`) |
| GET | `/health` | Saúde de banco e broker (503 se degradado) |
| GET | `/` | Dashboard web |

## Desenvolvimento

Com [Nix + direnv](docs/DESAFIO.md#ambiente-de-desenvolvimento) (`direnv allow`) ou apenas [uv](https://docs.astral.sh/uv/):

```bash
uv sync                 # instala Python 3.13 + dependências
make lint               # ruff check + format check
make typecheck          # mypy (strict)
make test               # testes unitários (rápidos, sem Docker)
make test-integration   # testes de integração (Testcontainers, requer Docker)
make up / make down     # docker compose
```

Sem Docker disponível, os testes de integração são pulados com aviso — os unitários rodam sempre.

## Testes

- **Unitários** (`tests/unit`): parsers com fixtures HTML reais salvas dos sites (células vazias, saldo negativo, flag de best picture, títulos com espaços), ciclo de vida do job no processor (sucesso, retry, falha final, idempotência, falha parcial do `all`), mapeamento outcome→ack/nack do consumer, serviço de enfileiramento e todos os endpoints da API (TestClient + publisher fake).
- **Integração** (`tests/integration`, Testcontainers): migrações e repositórios contra PostgreSQL real; persistência, requeue e roteamento para DLQ contra RabbitMQ real; fluxo completo API → fila → worker → banco → API com crawler stub (o desafio dispensa crawling real nos testes), cobrindo conclusão, retries limitados até DLQ e a fonte combinada.

## CI/CD

`.github/workflows/ci.yml`: **lint** (ruff + mypy) → **testes unitários** (com cobertura) → **testes de integração** (Testcontainers) → **build** da imagem (Buildx + cache) → **push para GCR** (somente push na `main`).

Para habilitar o push, configure os secrets do repositório:

| Secret | Conteúdo |
|---|---|
| `GCP_PROJECT_ID` | ID do projeto no Google Cloud |
| `GCP_SA_KEY` | JSON da service account com papel `roles/storage.admin` (GCR usa GCS) |

Sem os secrets o passo de push é pulado com aviso — o pipeline continua verde em forks. A imagem é tagueada com o SHA do commit e `latest`.

> **Nota:** o Container Registry (gcr.io) está deprecado pelo Google em favor do **Artifact Registry**. O pipeline usa `gcr.io` conforme o enunciado; a migração exigiria apenas trocar o registry para `<region>-docker.pkg.dev` e o papel da service account para `roles/artifactregistry.writer`.

## Estrutura

```
src/app/
├── api/            # FastAPI: rotas, dependências, error handlers
├── core/           # settings (pydantic-settings), logging estruturado, enums, exceções
├── crawlers/       # hockey (httpx+bs4) e oscar (selenium), parsers puros, registry
├── db/             # models SQLAlchemy 2.0, sessão, repositórios
├── messaging/      # contrato da mensagem, topologia AMQP, publisher
├── schemas/        # DTOs de coleta e schemas da API
├── services/       # orquestração job + publicação
├── static/         # dashboard web (HTML/JS puro, servido pela API)
└── worker/         # consumer, processor (ciclo de vida do job), entrypoint
alembic/            # migrações
tests/unit          # rápidos, sem rede e sem Docker
tests/integration   # Testcontainers (PostgreSQL + RabbitMQ)
```
