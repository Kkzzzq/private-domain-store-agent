from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.quality import report_batches
from test_quality import operator
from test_quality_report_batches import fixture_run


def test_hourly_limit_keeps_all_reports_in_hour_and_date_filter(client):
    _,uid=operator(client)
    latest=datetime(2026,10,21,4,30)
    with SessionLocal() as db:
        ids=[fixture_run(db,uid,'RF01',created=latest+timedelta(seconds=n)) for n in range(103)]
        for hour in range(1,102):fixture_run(db,uid,'RF01',created=latest-timedelta(hours=hour))
        rows=report_batches.listing(db)
        assert len(rows)==202
        assert set(ids).issubset({r['id'] for r in rows})
        stamps=[r['created_at'].replace(minute=0,second=0,microsecond=0) for r in rows]
        assert len(set(stamps))==100
        from datetime import date
        day=report_batches.listing(db,date(2026,10,21))
        assert len(day)==115
        assert report_batches.listing(db,date(2026,10,22))==[]
