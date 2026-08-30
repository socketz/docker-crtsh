# docker-crtsh — crt.sh ecosystem Docker deployment

Docker deployment of the **crt.sh** ecosystem for Certificate Transparency (CT)
certificate search and monitoring.

It includes a PostgreSQL 18 database with the `libx509pq` (C), `libocsppq` and
`libzlintpq` (Go via plgo) extensions and the `certwatch` schema, plus the
`ct_monitor`, `crl_monitor`, `ocsp_monitor`, `cert_processor` daemons and the
`crtsh-web` search frontend.

## Requirements

- Docker with Docker Compose.
- Free ports: `5432` (postgres), `8880`/`8881` (crtsh-web).
- Internet access during the build (clones of the upstream repos and download
  of the Go toolchain).

## How to deploy

```bash
docker compose up --build -d
```

This brings up six containers:

| Service | Container | Purpose |
|---|---|---|
| postgres | `crtsh-postgres` | PostgreSQL 18 + extensions + `certwatch` schema + `ct_log` seed |
| ct_monitor | `crtsh-ct-monitor` | Ingests certificates from the CT logs (table `ct_log`) |
| crl_monitor | `crtsh-crl-monitor` | Verifies the discovered CRLs |
| ocsp_monitor | `crtsh-ocsp-monitor` | Verifies the discovered OCSP responders |
| cert_processor | `crtsh-cert-processor` | Discovers CDP/OCSP/AIA URLs (feeds crl/ocsp_monitor) and maintains the CA counters |
| crtsh-web | `crtsh-frontend` | Certificate search frontend |

## Warnings

- **The database grows fast, reaching several gigabytes quickly.** `ct_monitor`
  ingests every certificate from the active CT logs (each log contains
  millions of certificates), and `cert_processor` then populates the CRL/OCSP
  tables and the CA counters. Plan for sufficient disk space (start with at
  least ~20-50 GB free) and be aware that the `postgres_data` volume keeps
  growing as long as the monitors run.
- **The data starts being built from the moment the stack first runs.** This
  deployment only records certificates as they are ingested from the CT logs
  from that point onward (plus the backfill of the log ranges still active).
  It does **not** contain historical certificates issued before your first
  start. If you need older data, you must start the ingestion earlier or source
  it externally.

## How to verify

```bash
# Containers are up
docker ps

# Installed extensions
docker exec crtsh-postgres psql -U certwatch -d certwatch -c '\dx'

# The certificate table grows with ct_monitor ingestion
docker exec crtsh-postgres psql -U certwatch -d certwatch -c 'SELECT count(*) FROM certificate;'

# ct_monitor ingesting (batches of "Records written")
docker logs -f crtsh-ct-monitor

# cert_processor doing the backfill (batches of "Certificates Processed")
docker logs -f crtsh-cert-processor

# Web: certificate search
curl -s http://localhost:8880/          # homepage
curl -s "http://localhost:8880/?q=example.com"
```

## Configuration

- **Credentials**: configured via environment. The postgres password is set
  with `POSTGRES_PASSWORD` (default `certwatch_pass`) and propagated to the
  monitors and `cert_processor`. Example:

  ```bash
  export POSTGRES_PASSWORD=change_me
  docker compose up --build -d
  ```

- **Monitor configs** (mounted as read-only volumes):
  - `ct_monitor/config.yaml`
  - `crl_monitor/crl_monitor.toml`
  - `ocsp_monitor/ocsp_monitor.toml`
  - `cert_processor/config.yaml`

## Seeding the `ct_log` table

`ct_monitor` reads the log list from the `ct_log` table. The initial seed is
generated and installed automatically on the first postgres start
(`db/init/20_seed_ct_logs.sql`). To regenerate it:

```bash
python scripts/generate_ct_log_seed.py --active-patterns "Argon2026h2,Xenon2026h2"
```

The generated file overwrites `db/init/20_seed_ct_logs.sql`. Adding a new log
in the future amounts to an `INSERT` in that table (ct_monitor re-syncs every
`getSTHFrequency`).

## Maintenance

While `ct_monitor` ingests at high volume, keep the statistics fresh so the
planner uses the GIN `identities()` indexes for full-text search:

```sql
VACUUM ANALYZE certificate;
```

> If full-text search becomes slow after heavy ingestion, run
> `VACUUM ANALYZE certificate;` (and, if needed, `REINDEX` during a low
> activity window) against the `certificate` partitions.

## Scope notes

- This deployment covers **monitoring and search** of CT certificates, the
  same purpose as https://crt.sh.
- **`ctsubmit`** (submitting chains to CT logs to collect SCTs) and
  **`ctlint`** (CT compliance auditing) are **out of scope**: they are
  independent services/CLIs that do not belong to the monitoring/search loop
  over the `certwatch` database.
- Full signature verification of CRLs/OCSP per issuer requires issuer
  identification (the `find_issuer` job), which is out of scope here.

## License

This repository (and the components it deploys, upstream crt.sh by Sectigo)
is distributed under the **GNU General Public License v3.0**. See
`LICENSE.md`.
