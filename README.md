# Promptchived

Promptchived is a private local web application for reading and searching ChatGPT and Gemini exports. It stores data in PostgreSQL, uses PostgreSQL Full Text Search for keyword retrieval, and provides semantic search through local `intfloat/multilingual-e5-small` embeddings and pgvector.

The interface supports English and Indonesian. English is the default, and the selected language is remembered in the browser.

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

## Testing

```powershell
pytest
```

To run the PostgreSQL idempotency test, create a separate test database whose name contains `test`, set `PROMPTCHIVED_TEST_DATABASE_URL`, and run `pytest`. A guard prevents this test from targeting the regular application database.

## Backup and unavailable exports

Text, metadata, indexes, and attachment references are stored in PostgreSQL. Attachment files remain in their original export folders. Back up both:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -U promptchived -Fc promptchived -f promptchived.dump
```

If an export folder is moved, disconnected, or deleted, imported text and search remain available. Attachment previews and rescanning require the original folder.
