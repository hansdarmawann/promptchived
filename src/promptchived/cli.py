import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from .config import get_settings
from .db import get_session_factory
from .importers.manifests import infer_source_root
from .models import Source
from .services.import_jobs import enqueue_scan, run_worker


def migrate() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(config, "head")


def bootstrap_manifest(path: Path, provider: str) -> Source:
    root = infer_source_root(path)
    if root is None or not root.is_dir():
        raise SystemExit(f"Source folder from {path} was not found: {root}")
    session_factory = get_session_factory()
    with session_factory() as session:
        existing = session.scalar(select(Source).where(Source.root_path == str(root.resolve())))
        if existing:
            return existing
        source = Source(
            name=f"{provider.capitalize()} · {root.name}",
            provider=provider,
            root_path=str(root.resolve()),
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return source


def enqueue_all() -> int:
    count = 0
    session_factory = get_session_factory()
    with session_factory() as session:
        for source in session.scalars(select(Source).where(Source.enabled.is_(True))):
            enqueue_scan(session, source)
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="promptchived")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="Run database migrations")
    serve = subparsers.add_parser("serve", help="Run the web application")
    serve.add_argument("--reload", action="store_true")
    worker = subparsers.add_parser("worker", help="Run the import and embedding worker")
    worker.add_argument("--once", action="store_true")
    bootstrap = subparsers.add_parser("bootstrap", help="Register sources from 1.txt and 2.txt")
    bootstrap.add_argument("--gemini-manifest", type=Path, default=Path("1.txt"))
    bootstrap.add_argument("--chatgpt-manifest", type=Path, default=Path("2.txt"))
    subparsers.add_parser("scan-all", help="Queue a scan for every source")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "serve":
        import uvicorn

        settings = get_settings()
        uvicorn.run(
            "promptchived.main:app",
            host=settings.host,
            port=settings.port,
            reload=args.reload,
        )
    elif args.command == "worker":
        run_worker(once=args.once)
    elif args.command == "bootstrap":
        gemini = bootstrap_manifest(args.gemini_manifest, "gemini")
        chatgpt = bootstrap_manifest(args.chatgpt_manifest, "chatgpt")
        print(f"Registered: {gemini.root_path}")
        print(f"Registered: {chatgpt.root_path}")
    elif args.command == "scan-all":
        print(f"Queued {enqueue_all()} sources.")


if __name__ == "__main__":
    main()
