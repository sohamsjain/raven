from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
import sqlalchemy as sa
import sqlalchemy.orm as so
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login
from app.search import add_to_index, remove_from_index, query_index, create_index


class SearchableMixin(object):
    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return [], 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        query = sa.select(cls).where(cls.id.in_(ids)).order_by(
            db.case(*when, value=cls.id))
        return db.session.scalars(query).all(), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        # First create/update the index with proper mappings
        create_index(cls.__tablename__, cls)
        # Then reindex all objects
        for obj in db.session.scalars(sa.select(cls)):
            add_to_index(cls.__tablename__, obj)

    @classmethod
    def init_index(cls):
        # Initialize/reset the index with proper mappings
        create_index(cls.__tablename__, cls)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)


class AlertType:
    CROSS_OVER = "Crossing Over"
    CROSS_UNDER = "Crossing Under"


class AlertStatus:
    ACTIVE = "Active"
    TRIGGERED = "Triggered"


class ZoneType:
    LONG = "Long Zone"
    SHORT = "Short Zone"


class ZoneStatus:
    ACTIVE = "Active"
    ENTRY_HIT = "Entry Hit"
    STOPLOSS_HIT = "Stoploss Hit"
    TARGET_HIT = "Target Hit"
    FAILED = "Failed"


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class User(SearchableMixin, UserMixin, db.Model):
    __searchable__ = ['name']
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    is_admin: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False, nullable=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(100))
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    phone_number: so.Mapped[str] = so.mapped_column(sa.String(20), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    created_at: so.Mapped[datetime] = so.mapped_column(index=True,
                                                       default=lambda: datetime.now(timezone.utc))

    # Relationships
    alerts: so.Mapped[List[Alert]] = so.relationship(back_populates="user")
    zones: so.Mapped[List[Zone]] = so.relationship(back_populates="user")

    def __repr__(self):
        return f'<User {self.email}>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Ticker(SearchableMixin, db.Model):
    __searchable__ = ['symbol', 'name']
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    symbol: so.Mapped[str] = so.mapped_column(sa.String(20), nullable=False)
    exchange: so.Mapped[str] = so.mapped_column(sa.String(10), nullable=False)
    instrument_token: so.Mapped[int] = so.mapped_column(unique=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(100))
    last_price: so.Mapped[Optional[float]] = so.mapped_column(sa.Float)
    last_updated: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Relationships
    alerts: so.Mapped[List[Alert]] = so.relationship(back_populates="ticker")
    zones: so.Mapped[List[Zone]] = so.relationship(back_populates="ticker")

    def __repr__(self):
        return f'<Ticker {self.symbol}>'


class Alert(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    symbol: so.Mapped[str] = so.mapped_column(sa.String(20), nullable=False)
    type: so.Mapped[str] = so.mapped_column(sa.String(20), nullable=False)
    price: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False)
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default=AlertStatus.ACTIVE)
    created_at: so.Mapped[datetime] = so.mapped_column(index=True,
                                                       default=lambda: datetime.now(timezone.utc))
    triggered_at: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Foreign Keys
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    ticker_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('ticker.id'), index=True)

    # Relationships
    user: so.Mapped[User] = so.relationship(back_populates="alerts")
    ticker: so.Mapped[Ticker] = so.relationship(back_populates="alerts")

    def __repr__(self):
        return f'<Alert {self.ticker.symbol} {self.price}>'


class Zone(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    symbol: so.Mapped[str] = so.mapped_column(sa.String(20), nullable=False)
    type: so.Mapped[str] = so.mapped_column(sa.String(20), nullable=False)
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default=ZoneStatus.ACTIVE)

    # Price levels
    entry: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False)
    stoploss: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False)
    target: so.Mapped[float] = so.mapped_column(sa.Float, nullable=False)

    # Timestamps
    created_at: so.Mapped[datetime] = so.mapped_column(index=True,
                                                       default=lambda: datetime.now(timezone.utc))
    entry_at: so.Mapped[Optional[datetime]] = so.mapped_column()
    stoploss_at: so.Mapped[Optional[datetime]] = so.mapped_column()
    target_at: so.Mapped[Optional[datetime]] = so.mapped_column()
    failed_at: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Foreign Keys
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    ticker_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('ticker.id'), index=True)

    # Relationships
    user: so.Mapped[User] = so.relationship(back_populates="zones")
    ticker: so.Mapped[Ticker] = so.relationship(back_populates="zones")

    def __repr__(self):
        return f'<Zone {self.ticker.symbol} {self.type}>'

    @property
    def reward_to_risk_ratio(self) -> float:
        """Calculate reward to risk ratio: |target-entry|/|entry-stoploss|"""
        try:
            return abs(self.target - self.entry) / abs(self.entry - self.stoploss)
        except ZeroDivisionError:
            return 0.0

    @property
    def risk_per_unit(self) -> float:
        """Calculate risk per unit: |entry-stoploss|"""
        return abs(self.entry - self.stoploss)
