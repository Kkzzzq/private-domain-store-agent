"""SQLite compatibility for Chroma on older Linux distributions."""
def ensure_sqlite():
    import sqlite3
    if sqlite3.sqlite_version_info >= (3, 35, 0):
        return
    import sys
    try:
        import pysqlite3
    except ImportError:
        raise RuntimeError("Chroma 需要 SQLite 3.35+；请安装 pysqlite3-binary") from None
    if pysqlite3.sqlite_version_info < (3, 35, 0):
        raise RuntimeError("Chroma 需要 SQLite 3.35 或更新版本")
    sys.modules["sqlite3"] = pysqlite3
    sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2
