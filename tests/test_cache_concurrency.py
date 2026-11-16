"""Task 1 — WAL + busy_timeout sur les connexions partagees du cache.

Serveur web et sous-process d'analyse ouvrent setbuilder.db en meme temps :
WAL pour que les lecteurs (API) ne bloquent pas l'ecrivain (analyse),
busy_timeout pour absorber les verrous transitoires.
"""
from setbuilder.cache import open_cache


def test_open_cache_is_wal(tmp_path):
    conn = open_cache(str(tmp_path / "c.db"))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_busy_timeout_set(tmp_path):
    conn = open_cache(str(tmp_path / "c.db"))
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_concurrent_read_during_write_succeeds(tmp_path):
    # writer ouvre une transaction d'ecriture ; un 2e connecteur WAL lit sans "locked"
    db = str(tmp_path / "c.db")
    w = open_cache(db)
    r = open_cache(db)
    w.execute("INSERT INTO tracks (content_id) VALUES ('a')")  # write en cours (pas commit)
    # lecture concurrente : pas d'exception "database is locked"
    assert r.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] in (0, 1)
    w.commit()
