# Promptchived

[![CI](https://github.com/hansdarmawann/promptchived/actions/workflows/ci.yml/badge.svg)](https://github.com/hansdarmawann/promptchived/actions/workflows/ci.yml)

Promptchived is a private local web application for reading and searching ChatGPT and Gemini exports. It stores data in PostgreSQL, uses PostgreSQL Full Text Search for keyword retrieval, and provides semantic search through local `intfloat/multilingual-e5-small` embeddings and pgvector.

The interface supports English and Indonesian. English is the default, and the selected language is remembered in the browser.

## Why Promptchived?

Promptchived grew out of a simple concern: conversations with ChatGPT and Gemini can contain ideas, decisions, and personal context that matter over time, yet the platforms' memory and storage are not something we can rely on forever. Chats may be hard to find, account features may change, and keeping every conversation inside a hosted service leaves little control over a personal archive.

This project makes it possible to keep a private, searchable copy of your exported conversations on your own computer. Your history stays available even when it is no longer convenient—or possible—to rely on the original service as its long-term home.

## Requirements

- Windows 10/11 and 64-bit Python 3.12
- PostgreSQL 18 running locally
- Visual Studio Build Tools with the **Desktop development with C++** workload for building pgvector
- Free disk space for the embedding model, which is downloaded once into `.models`

## 1. Install pgvector for PostgreSQL 18

Open **x64 Native Tools Command Prompt for VS** as Administrator, then run:

```bat
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd %TEMP%
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

The final command writes to the PostgreSQL installation directory and therefore requires Administrator privileges. See the [official pgvector Windows instructions](https://github.com/pgvector/pgvector#windows) for additional details.

## 2. Create the database and environment

Connect with a PostgreSQL administrator account. Replace the password in this example:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -d postgres
```

```sql
CREATE ROLE promptchived LOGIN PASSWORD 'replace-this-password';
CREATE DATABASE promptchived OWNER promptchived;
\c promptchived
CREATE EXTENSION vector;
```

Set up the application:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env`, especially the password in `PROMPTCHIVED_DATABASE_URL`, then run:

```powershell
promptchived migrate
```

## 3. Register and import exports

The optional `1.txt` and `2.txt` manifests contain export file locations for the initial source registration. They are ignored by Git and are no longer needed after the sources have been registered in PostgreSQL.

```powershell
promptchived bootstrap
promptchived scan-all
```

You can also register folders directly from the home page. The ChatGPT provider discovers `conversations*.json`; the Gemini provider discovers `MyActivity*.html`. Files with unchanged hashes are skipped.

Run the worker in a separate terminal:

```powershell
promptchived worker
```

Text is stored before embeddings are generated. If model setup fails, full-text search remains available and the job is marked `partial`. Scan the source again after the model becomes available to resume embedding generation.

## 4. Run the web application

```powershell
promptchived serve --reload
```

Open <http://127.0.0.1:8765>. The application binds only to the loopback interface and has no login because it is intended for a single user on a local computer. API documentation is available at <http://127.0.0.1:8765/docs>.

## Docker Compose

Docker Compose can run the web application, worker, migrations, PostgreSQL 18, and pgvector as one local stack. PostgreSQL is only available to the other containers; the web interface remains bound to `127.0.0.1:8765`.

Create the Docker environment file:

```powershell
Copy-Item .env.docker.example .env.docker
```

Edit `.env.docker`. Set a database password containing URL-safe characters and point `PROMPTCHIVED_ARCHIVE_PATH` to the common parent of the ChatGPT and Gemini export folders. Use forward slashes for a Windows path:

```dotenv
PROMPTCHIVED_DB_PASSWORD=replace-this-password
PROMPTCHIVED_ARCHIVE_PATH=G:/hadama10/backups/account-name
```

Start the complete stack:

```powershell
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
```

Open <http://127.0.0.1:8765>. Register source folders using their container paths, such as `/archives/chatgpt` and `/archives/gemini`. The host archive mount is read-only. The first semantic search or embedding job downloads the model into the shared `promptchived-models` volume.

Useful commands:

```powershell
docker compose --env-file .env.docker logs -f web worker
docker compose --env-file .env.docker restart web worker
docker compose --env-file .env.docker down
```

`docker compose down` keeps the database and model volumes. Adding `--volumes` deletes the containerized database and model cache.

### Move the existing native database into Docker

Create a dump from the current Windows PostgreSQL instance before starting the complete stack:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -U promptchived -Fc promptchived -f promptchived.dump
docker compose --env-file .env.docker up -d database
docker compose --env-file .env.docker cp promptchived.dump database:/tmp/promptchived.dump
docker compose --env-file .env.docker exec database pg_restore -U promptchived -d promptchived --clean --if-exists /tmp/promptchived.dump
```

Update the restored Windows source paths to their container paths, then start the remaining services:

```powershell
docker compose --env-file .env.docker exec database psql -U promptchived -d promptchived -c "UPDATE sources SET root_path = '/archives/chatgpt' WHERE provider = 'chatgpt'; UPDATE sources SET root_path = '/archives/gemini' WHERE provider = 'gemini';"
docker compose --env-file .env.docker up -d
```

The native PostgreSQL service can remain installed because the Compose database does not publish port `5432` to Windows.

## Testing

```powershell
pytest
```

To run the PostgreSQL idempotency test, create a separate test database whose name contains `test`, set `PROMPTCHIVED_TEST_DATABASE_URL`, and run `pytest`. A guard prevents this test from targeting the regular application database.

## CI and releases

GitHub Actions runs compilation, tests, Docker Compose validation, and distribution builds for every pull request and push to `main`. PostgreSQL integration tests remain skipped unless a dedicated test database is configured.

To publish a GitHub Release, update `project.version` in `pyproject.toml`, commit the change, then create and push a matching version tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The release workflow verifies that the tag matches `project.version`, builds the wheel and source distribution, and attaches both files to the generated GitHub Release.

## Backup and unavailable exports

Text, metadata, indexes, and attachment references are stored in PostgreSQL. Attachment files remain in their original export folders. Back up both:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -U promptchived -Fc promptchived -f promptchived.dump
```

If an export folder is moved, disconnected, or deleted, imported text and search remain available. Attachment previews and rescanning require the original folder.
