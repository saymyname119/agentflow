import hashlib
import json
import time
import uuid

from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text,
                        and_, create_engine, event, or_, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

metadata = MetaData()
jobs = Table("jobs", metadata,
    Column("id", String(128), primary_key=True), Column("repository", String(256), nullable=False),
    Column("number", Integer, nullable=False), Column("status", String(20), nullable=False, index=True),
    Column("attempts", Integer, nullable=False), Column("available_at", Float, nullable=False),
    Column("lease_until", Float, nullable=False), Column("lease_token", String(64)),
    Column("error", Text), Column("decision_id", String(64)))
decisions = Table("decisions", metadata,
    Column("id", String(64), primary_key=True), Column("fingerprint", String(64), nullable=False),
    Column("request_id", String(128), unique=True, nullable=False),
    Column("repository", String(256), nullable=False, index=True), Column("number", Integer, nullable=False),
    Column("head_sha", String(40), nullable=False), Column("base_sha", String(40), nullable=False),
    Column("author", String(256), nullable=False), Column("evidence", Text, nullable=False),
    Column("recommendation", Text, nullable=False), Column("created_at", Float, nullable=False),
    Column("resolution", String(20)), Column("revision", Integer, nullable=False))
audit = Table("audit", metadata,
    Column("id", String(64), primary_key=True), Column("decision_id", String(64), nullable=False, index=True),
    Column("at", Float, nullable=False), Column("actor", String(256), nullable=False),
    Column("action", String(32), nullable=False), Column("reason", Text, nullable=False))
publications = Table("publications", metadata,
    Column("decision_id", String(64), primary_key=True), Column("state", String(24), nullable=False),
    Column("review_id", String(64)), Column("url", Text), Column("error", String(64)))


def fingerprint(snapshot, policy):
    # Hash patches for change detection; do not persist raw source or credentials.
    data = {"snapshot": snapshot.model_dump(mode="json"), "policy": policy.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, url):
        sqlite = make_url(url).get_backend_name() == "sqlite"
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15}
                                    if sqlite else {})
        if sqlite:
            @event.listens_for(self.engine, "connect")
            def sqlite_settings(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
        metadata.create_all(self.engine)

    def enqueue(self, delivery_id, repository, number):
        try:
            with self.engine.begin() as db:
                db.execute(jobs.insert().values(id=delivery_id, repository=repository, number=number,
                    status="queued", attempts=0, available_at=time.time(), lease_until=0))
            return True
        except IntegrityError:
            return False

    def claim(self, now=None, lease_seconds=120):
        now = time.time() if now is None else now
        eligible = and_(jobs.c.attempts < 5, or_(
            and_(jobs.c.status.in_(["queued", "retry"]), jobs.c.available_at <= now),
            and_(jobs.c.status == "running", jobs.c.lease_until <= now)))
        with self.engine.begin() as db:
            db.execute(update(jobs).where(jobs.c.status == "running", jobs.c.lease_until <= now,
                jobs.c.attempts >= 5).values(status="dead", error="Worker lease expired after final attempt"))
            candidate = db.execute(select(jobs.c.id).where(eligible).order_by(jobs.c.available_at).limit(1)).scalar()
            if not candidate:
                return None
            result = db.execute(update(jobs).where(jobs.c.id == candidate, eligible).values(
                status="running", attempts=jobs.c.attempts + 1, lease_until=now + lease_seconds,
                lease_token=uuid.uuid4().hex))
            if result.rowcount != 1:
                return None
            return dict(db.execute(select(jobs).where(jobs.c.id == candidate)).mappings().one())

    def finish(self, job, decision_id=None, error=None):
        with self.engine.begin() as db:
            # An expired worker may not overwrite a newer worker's result.
            return db.execute(update(jobs).where(jobs.c.id == job["id"],
                jobs.c.lease_token == job["lease_token"], jobs.c.status == "running",
                jobs.c.lease_until > time.time()).values(
                    status=("dead" if job["attempts"] >= 5 else "retry") if error else "done",
                    error=error, decision_id=decision_id,
                    available_at=time.time() + min(300, 2 ** job["attempts"]), lease_until=0)).rowcount == 1

    def record(self, snapshot, recommendation, policy, request_id=None):
        fp = fingerprint(snapshot, policy)
        decision_id = uuid.uuid4().hex
        request_id = request_id or decision_id
        evidence = snapshot.model_dump(mode="json")
        for f in evidence["files"]:
            f.pop("patch", None)
        try:
            with self.engine.begin() as db:
                db.execute(decisions.insert().values(id=decision_id, fingerprint=fp, request_id=request_id,
                    repository=snapshot.repository, number=snapshot.number, head_sha=snapshot.head_sha,
                    base_sha=snapshot.base_sha, author=snapshot.author, evidence=json.dumps(evidence),
                    recommendation=recommendation.model_dump_json(), created_at=time.time(), revision=1))
                db.execute(audit.insert().values(id=uuid.uuid4().hex, decision_id=decision_id,
                    at=time.time(), actor="policy", action="evaluated", reason=policy.version))
            return decision_id
        except IntegrityError:
            with self.engine.connect() as db:
                return db.execute(select(decisions.c.id).where(decisions.c.request_id == request_id)).scalar_one()

    def decision(self, decision_id):
        with self.engine.connect() as db:
            row = db.execute(select(decisions).where(decisions.c.id == decision_id)).mappings().first()
            return self.decode(row) if row else None

    @staticmethod
    def decode(row):
        result = dict(row)
        result["evidence"] = json.loads(result["evidence"])
        result["recommendation"] = json.loads(result["recommendation"])
        return result

    def recent(self):
        with self.engine.connect() as db:
            return [self.decode(row) for row in db.execute(select(decisions).order_by(
                decisions.c.created_at.desc()).limit(100)).mappings()]

    def resolve(self, decision_id, revision, actor, action, reason):
        with self.engine.begin() as db:
            updated = db.execute(update(decisions).where(decisions.c.id == decision_id,
                decisions.c.revision == revision, decisions.c.resolution.is_(None)).values(
                    resolution=action, revision=revision + 1))
            if updated.rowcount != 1:
                return False
            db.execute(audit.insert().values(id=uuid.uuid4().hex, decision_id=decision_id,
                at=time.time(), actor=actor, action=action, reason=reason))
            return True

    def events(self, decision_id):
        with self.engine.connect() as db:
            return [dict(r) for r in db.execute(select(audit).where(
                audit.c.decision_id == decision_id).order_by(audit.c.at)).mappings()]

    def job(self, job_id):
        with self.engine.connect() as db:
            row = db.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            return dict(row) if row else None

    def reserve_publication(self, decision_id):
        try:
            with self.engine.begin() as db:
                db.execute(publications.insert().values(decision_id=decision_id, state="sending"))
            return True
        except IntegrityError:
            return False

    def publication(self, decision_id):
        with self.engine.connect() as db:
            row = db.execute(select(publications).where(publications.c.decision_id == decision_id)).mappings().first()
            return dict(row) if row else None

    def finish_publication(self, decision_id, actor, result=None, error=None):
        with self.engine.begin() as db:
            db.execute(update(publications).where(publications.c.decision_id == decision_id).values(
                state="uncertain" if error else "published", error=error,
                review_id=str(result["review_id"]) if result else None, url=result["url"] if result else None))
            db.execute(audit.insert().values(id=uuid.uuid4().hex, decision_id=decision_id,
                at=time.time(), actor=actor, action="publication_uncertain" if error else "published",
                reason=error or str(result["review_id"])))
