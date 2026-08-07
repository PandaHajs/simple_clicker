from datetime import datetime, timedelta, timezone
from os import environ
from secrets import token_hex

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.mutable import MutableDict

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = environ.get("SECRET_KEY", "dev")

db = SQLAlchemy(app)
ws = SocketIO(app, cors_allowed_origins=environ.get("CORS_ORIGINS", "*"), async_mode="threading")


class User(db.Model):
    __tablename__ = "users"

    session = db.Column(db.String(120), unique=True, nullable=False, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    score = db.Column(db.Integer, nullable=False, default=0)
    currentPoints = db.Column(db.Integer, nullable=False, default=0)
    last_click_at = db.Column(db.DateTime(timezone=True), nullable=True)
    upgrades = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=lambda: {"click_power": 1},
)

    def json(self):
        return {
            "session": self.session,
            "username": self.username,
            "score": self.score,
            "currentPoints": self.currentPoints,
            "upgrades": self.upgrades,
        }

class Upgrades(db.Model):
    __tablename__ = "upgrades"

    id = db.Column(db.Integer, primary_key=True)
    upgrade_name = db.Column(db.String(80), unique=True, nullable=False)
    upgrade_cost = db.Column(db.Integer, nullable=False)
    upgrade_effect = db.Column(db.String(120), nullable=False)

    def json(self):
        return {
            "id": self.id,
            "upgrade_name": self.upgrade_name,
            "upgrade_cost": self.upgrade_cost,
            "upgrade_effect": self.upgrade_effect,
        }


with app.app_context():
    db.create_all()
    try:
        upgrades_data = [
            {"id": 1, "upgrade_name": "click_power", "upgrade_cost": 10, "upgrade_effect": "+1 click power"},
        ]
        for upgrade_data in upgrades_data:
            upgrade = Upgrades(**upgrade_data)
            db.session.add(upgrade)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error occurred while adding upgrades: {e}")

def serialize_leaderboard():
    users = User.query.order_by(User.score.desc(), User.username.asc()).limit(10).all()
    return [user.json() for user in users]


def fetch_user(session_id):
    if not session_id:
        return None
    return User.query.filter_by(session=session_id).first()


@app.route("/test", methods=["GET"])
def test():
    return jsonify({"message": "API is working!"}), 200


@app.route("/api/flask/create_user", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()

    if not username:
        return jsonify({"message": "Username is required"}), 400

    user = User(username=username, session=token_hex(16))
    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Username already exists"}), 409

    return jsonify(user.json()), 201


@app.route("/api/flask/get_leaderboard", methods=["GET"])
def get_leaderboard():
    users = serialize_leaderboard()
    return jsonify(users), 200


@app.route("/api/flask/get_score", methods=["GET"])
def get_score():
    session_id = request.args.get("session")

    if not session_id:
        return jsonify({"message": "Session is required"}), 400

    user = fetch_user(session_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    return jsonify({"score": user.score, "currentPoints": user.currentPoints}), 200


@app.route("/api/flask/user/<string:username>", methods=["GET"])
def get_user_by_username(username):
    user = User.query.filter_by(username=username).first()
    if user:
        return jsonify(user.json()), 200
    return jsonify({"message": "User not found"}), 404

def get_upgrade_cost(upgrade, user):
    level = user.upgrades.get(upgrade.upgrade_name, 0)
    return int(upgrade.upgrade_cost * (1.2 ** level))

@app.route("/api/flask/get_upgrades", methods=["GET"])
def get_upgrades():
    user = fetch_user(request.args.get("session"))
    upgrades = Upgrades.query.all()

    result = []

    for upgrade in upgrades:
        result.append({
            "id": upgrade.id,
            "upgrade_name": upgrade.upgrade_name,
            "upgrade_effect": upgrade.upgrade_effect,
            "upgrade_cost": (
                get_upgrade_cost(upgrade, user)
                if user
                else upgrade.upgrade_cost
            ),
        })

    return jsonify(result), 200

@app.route("/api/flask/get_user_upgrades", methods=["GET"])
def get_user_upgrades():
    session_id = request.args.get("session")

    if not session_id:
        return jsonify({"message": "Session is required"}), 400

    user = fetch_user(session_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    return jsonify({"upgrades": user.upgrades}), 200



@ws.on("buy_upgrade")
def buy_upgrade(data):
    payload = data or {}
    session_id = payload.get("session")
    upgrade_name = payload.get("upgradeName")

    if not session_id or not upgrade_name:
        return {"ok": False, "message": "Session and upgrade_name are required"}

    user = fetch_user(session_id)
    if not user:
      return {"ok": False, "message": "User not found"}

    upgrade = Upgrades.query.filter_by(upgrade_name=upgrade_name).first()
    if not upgrade:
        return {"ok": False, "message": "Upgrade not found"}

    upgrade_cost = get_upgrade_cost(upgrade, user)

    if user.currentPoints < upgrade_cost:
        return {"ok": False, "message": "Not enough points to buy this upgrade"}

    user.currentPoints -= upgrade_cost
    user.upgrades[upgrade_name] = user.upgrades[upgrade_name] + 1 if user.upgrades[upgrade_name] != 0 else 1
    
    db.session.commit()
    ws.emit("upgrade_update", {
    "upgrades": user.upgrades,
    "upgrade": {
        "upgrade_name": upgrade.upgrade_name,
        "upgrade_effect": upgrade.upgrade_effect,
        "upgrade_cost": get_upgrade_cost(upgrade, user),
    }
}, to=request.sid)
    ws.emit("score_update", {"score": user.score, "currentPoints": user.currentPoints}, to=request.sid)
    return {"ok": True, "message": "Upgrade purchased successfully", "upgrades": user.upgrades, "score": user.score, "currentPoints": user.currentPoints}

@ws.on("join")
def handle_join(data):
    payload = data or {}
    session_id = payload.get("session")
    user = fetch_user(session_id)

    if not user:
        return {"ok": False, "message": "User not found"}

    ws.emit(
        "score_state",
        {"score": user.score, "currentPoints": user.currentPoints, "leaderboard": serialize_leaderboard(), "upgrades": user.upgrades},
        to=request.sid,
    )
    return {"ok": True, "score": user.score, "currentPoints": user.currentPoints, "upgrades": user.upgrades}


@ws.on("click")
def handle_click(data):
    payload = data or {}
    session_id = payload.get("session")
    user = fetch_user(session_id)

    if not user:
        return {"ok": False, "message": "User not found"}

    now = datetime.now(timezone.utc)
    if user.last_click_at and now - user.last_click_at < timedelta(milliseconds=100):
        return {"ok": False, "message": "You are clicking too fast"}

    user.upgrades = user.upgrades or {}
    click_power = user.upgrades.get("click_power", 1)

    user.score += click_power
    user.currentPoints += click_power
    user.last_click_at = now
    db.session.commit()

    leaderboard = serialize_leaderboard()
    ws.emit("leaderboard_update", {"leaderboard": leaderboard})
    ws.emit("score_update", {"score": user.score, "currentPoints": user.currentPoints}, to=request.sid)

    return {"ok": True, "score": user.score}


if __name__ == "__main__":
    port = int(environ.get("PORT", 5000))
    ws.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)