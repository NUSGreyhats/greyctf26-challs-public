from app.db.session import Database


def bootstrap_schema() -> None:
    from app.core.config import settings

    dsn = settings.database_admin_url or settings.database_url
    with Database.bootstrap(dsn=dsn) as db:
        root = Database.project_root()
        shared_sql = _read_sql(root, "app/core/sql/shared_platform.sql")
        db.execute_script(shared_sql)
        db.execute_script(_read_sql(root, "app/stages/stage1/sql/pinpoint.sql"))
        db.execute_script(_read_sql(root, "app/stages/stage2/sql/queens.sql"))
        db.execute_script(_read_sql(root, "app/stages/stage3/sql/tango.sql"))
        db.execute_script(_read_sql(root, "app/core/sql/grant_app_role.sql"))


def _read_sql(root, relative_path: str) -> str:
    for candidate in (root / relative_path, root / "src/backend" / relative_path):
        if candidate.exists():
            return candidate.read_text()
    raise FileNotFoundError(f"Could not resolve SQL path for {relative_path}.")
