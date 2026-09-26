from datetime import datetime
from database import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    phone = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    last_login = db.Column(
        db.DateTime,
        nullable=True
    )

    last_logout = db.Column(
        db.DateTime,
        nullable=True
    )

    last_ip = db.Column(
        db.String(45),
        nullable=True
    )

    online = db.Column(
        db.Boolean,
        default=False
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sender = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    receiver = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    status = db.Column(
        db.String(20),
        default="pending"
    )

    delivered_at = db.Column(
        db.DateTime,
        nullable=True
    )

    read_at = db.Column(
        db.DateTime,
        nullable=True
    )


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    phone = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    ip_address = db.Column(
        db.String(45),
        nullable=True
    )

    login_time = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    logout_time = db.Column(
        db.DateTime,
        nullable=True
    )

    session_status = db.Column(
        db.String(20),
        default="active"
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    event_type = db.Column(
        db.String(50),
        nullable=False
    )

    phone = db.Column(
        db.String(20),
        nullable=True
    )

    ip_address = db.Column(
        db.String(45),
        nullable=True
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    timestamp = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    

class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    last_ip = db.Column(db.String(45), nullable=True)
