import hashlib
import json
import time
import uuid

from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text,
                        and_, create_engine, event, func, or_, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from .versions import POLICY_ENGINE_VERSION

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
review_heads = Table("review_heads", metadata,
    Column("repository", String(256), primary_key=True), Column("number", Integer, primary_key=True),
    Column("decision_id", String(64)))


def fingerprint(snapshot, policy):
    # Hash patches for change detection; do not persist raw source or credentials.
    data = {"engine_version": POLICY_ENGINE_VERSION, "snapshot": snapshot.model_dump(mode="json"), "policy": policy.model_dump(mode="json")}
    # GitHub list order is not review evidence. Preserve content, normalize only order.
    canonical = lambda item: json.dumps(item, sort_keys=True)
    for field in ("files", "checks"):
        data["snapshot"][field].sort(key=canonical)
    data["policy"]["required_checks"].sort(key=canonical)
    data["policy"]["sensitive_patterns"].sort()
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

    def ping(self):
        with self.engine.connect() as db:
            db.execute(select(1)).scalar_one()

    @staticmethod
    def _lock_review(db, repository, number):
        """Serialize recommendation creation and decision actions for one PR."""
        insert = sqlite_insert if db.dialect.name == "sqlite" else postgres_insert
        key = and_(review_heads.c.repository == repository, review_heads.c.number == number)
        db.execute(insert(review_heads).values(repository=repository, number=number).on_conflict_do_nothing())
        # A no-op UPDATE acquires the row's write lock on PostgreSQL and SQLite.
        db.execute(update(review_heads).where(key).values(decision_id=review_heads.c.decision_id))
        current = db.execute(select(review_heads.c.decision_id).where(key)).scalar_one()
        if current is None:
            # Lazily initialize the pointer for records created before this additive table.
            current = db.execute(select(decisions.c.id).where(decisions.c.repository == repository,
                decisions.c.number == number).order_by(decisions.c.created_at.desc(), decisions.c.id.desc()).limit(1)).scalar()
            if current:
                db.execute(update(review_heads).where(key).values(decision_id=current))
        return current

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

    def _record(self, db, snapshot, recommendation, policy, request_id):
        fp = fingerprint(snapshot, policy)
        decision_id = uuid.uuid4().hex
        self._lock_review(db, snapshot.repository, snapshot.number)
        existing = db.execute(select(decisions.c.id, decisions.c.fingerprint).where(
            decisions.c.request_id == request_id)).mappings().first()
        if existing:
            if existing["fingerprint"] != fp:
                raise ValueError("Idempotency key is already bound to different evidence")
            return existing["id"]
        evidence = snapshot.model_dump(mode="json")
        for f in evidence["files"]:
            f.pop("patch", None)
        db.execute(decisions.insert().values(id=decision_id, fingerprint=fp, request_id=request_id,
            repository=snapshot.repository, number=snapshot.number, head_sha=snapshot.head_sha,
            base_sha=snapshot.base_sha, author=snapshot.author, evidence=json.dumps(evidence),
            recommendation=recommendation.model_dump_json(), created_at=time.time(), revision=1))
        db.execute(audit.insert().values(id=uuid.uuid4().hex, decision_id=decision_id,
            at=time.time(), actor="policy", action="evaluated", reason=policy.version))
        db.execute(update(review_heads).where(review_heads.c.repository == snapshot.repository,
            review_heads.c.number == snapshot.number).values(decision_id=decision_id))
        return decision_id

    def record(self, snapshot, recommendation, policy, request_id=None):
        request_id = request_id or uuid.uuid4().hex
        try:
            with self.engine.begin() as db:
                return self._record(db, snapshot, recommendation, policy, request_id)
        except IntegrityError:
            with self.engine.connect() as db:
                existing = db.execute(select(decisions.c.id, decisions.c.fingerprint).where(
                    decisions.c.request_id == request_id)).mappings().first()
                if existing and existing["fingerprint"] == fingerprint(snapshot, policy):
                    return existing["id"]
            raise

    def complete(self, job, snapshot, recommendation, policy):
        """The lease fence, recommendation, audit event and job completion commit together."""
        with self.engine.begin() as db:
            fenced = db.execute(update(jobs).where(jobs.c.id == job["id"],
                jobs.c.lease_token == job["lease_token"], jobs.c.status == "running",
                jobs.c.lease_until > time.time()).values(status="done", lease_until=0, error=None))
            if fenced.rowcount != 1:
                return None
            decision_id = self._record(db, snapshot, recommendation, policy, job["id"])
            db.execute(update(jobs).where(jobs.c.id == job["id"]).values(decision_id=decision_id))
            return decision_id

    def is_current(self, decision_id):
        with self.engine.connect() as db:
            row = db.execute(select(decisions.c.repository, decisions.c.number).where(
                decisions.c.id == decision_id)).mappings().first()
            if not row:
                return False
            current = db.execute(select(review_heads.c.decision_id).where(
                review_heads.c.repository == row["repository"], review_heads.c.number == row["number"])).scalar()
            if current is None:
                current = db.execute(select(decisions.c.id).where(decisions.c.repository == row["repository"],
                    decisions.c.number == row["number"]).order_by(decisions.c.created_at.desc(), decisions.c.id.desc()).limit(1)).scalar()
            return current == decision_id

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

    def recent(self, repositories=None):
        with self.engine.connect() as db:
            query = select(decisions)
            if repositories is not None:
                query = query.where(func.lower(decisions.c.repository).in_([r.lower() for r in repositories]))
            return [self.decode(row) for row in db.execute(query.order_by(
                decisions.c.created_at.desc()).limit(100)).mappings()]

    def resolve(self, decision_id, revision, actor, action, reason):
        with self.engine.begin() as db:
            row = db.execute(select(decisions.c.repository, decisions.c.number).where(
                decisions.c.id == decision_id)).mappings().first()
            if not row or self._lock_review(db, row["repository"], row["number"]) != decision_id:
                return False
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
                row = db.execute(select(decisions.c.repository, decisions.c.number, decisions.c.resolution).where(
                    decisions.c.id == decision_id)).mappings().first()
                if not row or row["resolution"] != "approve" or self._lock_review(db, row["repository"], row["number"]) != decision_id:
                    return False
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
