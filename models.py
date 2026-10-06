import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    analyses = db.relationship(
        "Analysis", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    resumes = db.relationship(
        "Resume", backref="user", lazy=True, cascade="all, delete-orphan"
    )


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    filename = db.Column(db.String(200))
    role = db.Column(db.String(120))
    score = db.Column(db.Integer, nullable=False)
    result_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def data(self):
        return json.loads(self.result_json)


class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(120), default="Untitled resume")
    data_json = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def data(self):
        return json.loads(self.data_json)