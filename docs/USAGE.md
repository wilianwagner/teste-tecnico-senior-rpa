# Guia de Uso — Dashboard, API e Banco de Dados

Este guia mostra como operar o sistema depois de subir o ambiente:

```bash
docker compose up --build -d
```

| Serviço | Endereço | Credenciais |
|---|---|---|
| Dashboard web | http://localhost:8000 | — |
| API (Swagger UI) | http://localhost:8000/docs | — |
| API (ReDoc) | http://localhost:8000/redoc | — |
| PostgreSQL | localhost:5432 | usuário `rpa` · senha `rpa` · banco `rpa` |
| RabbitMQ management | http://localhost:15672 | usuário `rpa` · senha `rpa` |
| Selenium (grid status) | http://localhost:4444/wd/hub/status | — |

---

## 1. Dashboard

Acesse **http://localhost:8000**. O dashboard consome a própria API REST e permite:

- **Agendar coletas** — botões *Coletar Hockey*, *Coletar Oscar* e *Coletar Tudo* (equivalem aos `POST /crawl/*`).
- **Acompanhar jobs** — tabela com atualização automática a cada 4s: status (pendente → executando → concluído/falhou), tentativas, registros coletados, duração e mensagem de erro. Clique em um job para ver uma prévia dos dados coletados por ele.
- **Explorar resultados** — abas *Hockey Teams* e *Oscar Films* com o snapshot da última coleta completa, filtros por ano e por texto (time/título) e paginação.
- **Saúde do serviço** — indicador no topo (banco + fila), atualizado a cada 10s.

## 2. API

### Documentação interativa (Swagger)

A API é documentada automaticamente via OpenAPI:

- **http://localhost:8000/docs** — Swagger UI: schemas de request/response, códigos de erro por endpoint e execução interativa (botão *Try it out* dispara a chamada real).
- **http://localhost:8000/redoc** — mesma especificação em formato de leitura.
- **http://localhost:8000/openapi.json** — especificação OpenAPI crua (útil para gerar clients).

### Exemplos com curl

Agendar uma coleta (retorna imediatamente com o `job_id`):

```bash
curl -X POST http://localhost:8000/crawl/all
```

```json
{"job_id": "f170dd1c-1a1f-424b-ab72-990343957bd7", "source": "all", "status": "pending"}
```

Acompanhar o job (status: `pending` → `running` → `completed`/`failed`):

```bash
curl http://localhost:8000/jobs/f170dd1c-1a1f-424b-ab72-990343957bd7
```

```json
{
  "id": "f170dd1c-1a1f-424b-ab72-990343957bd7",
  "source": "all",
  "status": "completed",
  "attempts": 1,
  "records_collected": 669,
  "error_message": null,
  "created_at": "2026-09-01T16:41:12.483920Z",
  "started_at": "2026-09-01T16:41:12.612041Z",
  "finished_at": "2026-09-01T16:41:41.038712Z"
}
```

Listar jobs com filtros e paginação:

```bash
curl "http://localhost:8000/jobs?status=completed&source=all&limit=10&offset=0"
```

Dados coletados por um job específico (paginação por seção):

```bash
curl "http://localhost:8000/jobs/f170dd1c-1a1f-424b-ab72-990343957bd7/results?limit=5"
```

Snapshot consolidado (última coleta completa de cada fonte), com filtros:

```bash
curl "http://localhost:8000/results/hockey?year=1990&team=bruins"
curl "http://localhost:8000/results/oscar?year=2015&title=spotlight"
```

```json
{
  "items": [
    {"year": 2015, "title": "Spotlight", "nominations": 6, "awards": 2, "best_picture": true}
  ],
  "total": 1,
  "limit": 100,
  "offset": 0,
  "job_id": "f170dd1c-1a1f-424b-ab72-990343957bd7",
  "collected_at": "2026-09-01T16:41:41.038712Z"
}
```

Saúde do serviço (HTTP 200 saudável, 503 degradado):

```bash
curl http://localhost:8000/health
```

## 3. Banco de dados (PostgreSQL)

### psql pelo container

```bash
docker compose exec postgres psql -U rpa -d rpa
```

### Cliente gráfico (DBeaver, TablePlus, pgAdmin, DataGrip…)

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | `5432` |
| Banco | `rpa` |
| Usuário | `rpa` |
| Senha | `rpa` |

URL de conexão: `postgresql://rpa:rpa@localhost:5432/rpa`

### Esquema

| Tabela | Conteúdo |
|---|---|
| `jobs` | Ciclo de vida dos jobs: `id` (UUID), `source`, `status`, `attempts`, `records_collected`, `error_message`, `created_at`, `started_at`, `finished_at` |
| `hockey_team_stats` | Estatísticas por time/temporada, com FK `job_id` (a coleta que gerou a linha) |
| `oscar_films` | Filmes por ano de cerimônia, com FK `job_id` |
| `alembic_version` | Controle de migrações |

### Consultas úteis

```sql
-- Últimos jobs e seu resultado
SELECT id, source, status, attempts, records_collected, error_message, created_at
FROM jobs ORDER BY created_at DESC LIMIT 10;

-- Dados da última coleta completa de hockey
SELECT h.team_name, h.year, h.wins, h.losses, h.win_pct
FROM hockey_team_stats h
WHERE h.job_id = (
  SELECT id FROM jobs
  WHERE status = 'completed' AND source IN ('hockey', 'all')
  ORDER BY finished_at DESC LIMIT 1
)
ORDER BY h.year, h.team_name;

-- Vencedores de melhor filme por ano
SELECT year, title, nominations, awards
FROM oscar_films
WHERE best_picture ORDER BY year;

-- Volume coletado por job
SELECT j.id, j.source, j.finished_at,
       (SELECT count(*) FROM hockey_team_stats WHERE job_id = j.id) AS hockey_rows,
       (SELECT count(*) FROM oscar_films WHERE job_id = j.id) AS oscar_rows
FROM jobs j WHERE j.status = 'completed' ORDER BY j.finished_at DESC;
```

> Os dados são armazenados **por job** (auditável). Os endpoints `/results/*` já resolvem "a última coleta completa" — as queries acima replicam essa semântica em SQL.

## 4. RabbitMQ

Management UI em **http://localhost:15672** (`rpa`/`rpa`):

- **Queues** → `crawl_jobs`: fila principal consumida pelo worker (prefetch 1, ack manual).
- **Queues** → `crawl_jobs.dlq`: dead-letter queue — mensagens que esgotaram as tentativas (`CRAWL_MAX_ATTEMPTS`, padrão 3). Inspecione com *Get messages* para ver o payload `{job_id, source}`.
- **Exchanges** → `crawler` (roteamento principal) e `crawler.dlx` (dead-letter exchange).

## 5. Logs e troubleshooting

```bash
docker compose logs -f api worker   # logs estruturados (JSON) com job_id correlacionado
docker compose ps                   # estado e healthchecks dos serviços
docker compose down -v              # derruba tudo e apaga o volume do banco
```

- Job preso em `pending`: verifique o worker (`docker compose logs worker`) e a fila no management.
- Job `failed`: a coluna `error_message` (API, dashboard ou banco) indica a fonte e o motivo; a mensagem correspondente estará na DLQ.
- Selenium: `http://localhost:4444/wd/hub/status` deve responder `ready`; o worker depende dele apenas para a fonte `oscar`.
