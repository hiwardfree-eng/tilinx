from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(128), nullable=False)
    detail = db.Column(db.Text, default="")
    level = db.Column(db.String(16), default="info")
    timestamp = db.Column(db.String(32), default=lambda: datetime.utcnow().isoformat())

def init_db(app):
    db.create_all()
    if Log.query.count() == 0:
        db.session.add(Log(event="system_start", detail="TilinX Website initialized"))
        db.session.commit()
