# AgentEval Foundry

Run the deterministic evaluation pipeline without persistence:

```bash
python -m scripts.run_suite
```

## PostgreSQL Persistence

Start PostgreSQL and apply the schema:

```bash
docker compose up -d postgres
alembic upgrade head
```

Run and persist a complete evaluation bundle:

```bash
python -m scripts.run_suite --persist
```

Stop PostgreSQL:

```bash
docker compose down
```

pgAdmin is optional and is not included.
