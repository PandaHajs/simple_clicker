from datetime import datetime, timedelta, timezone
from os import environ
from secrets import token_hex

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = environ.get("SECRET_KEY", "dev")

db = SQLAlchemy(app)
socketio_path = environ.get("SOCKETIO_PATH") or ("api/flask/socket.io" if environ.get("VERCEL") else "socket.io")
ws = SocketIO(
    app,
    cors_allowed_origins=environ.get("CORS_ORIGINS", "*"),
    async_mode="threading",
    socketio_path=socketio_path,
)


class User(db.Model):
    __tablename__ = "users"

    session = db.Column(db.String(120), unique=True, nullable=False, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    score = db.Column(db.Integer, nullable=False, default=0)
    last_click_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def json(self):
        return {
            "session": self.session,
            "username": self.username,
            "score": self.score,
        }


with app.app_context():
    db.create_all()


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

    return jsonify({"score": user.score}), 200


@app.route("/api/flask/user/<string:username>", methods=["GET"])
def get_user_by_username(username):
    user = User.query.filter_by(username=username).first()
    if user:
        return jsonify(user.json()), 200
    return jsonify({"message": "User not found"}), 404


@ws.on("join")
def handle_join(data):
    payload = data or {}
    session_id = payload.get("session")
    user = fetch_user(session_id)

    if not user:
        return {"ok": False, "message": "User not found"}

    ws.emit(
        "score_state",
        {"score": user.score, "leaderboard": serialize_leaderboard()},
        to=request.sid,
    )
    return {"ok": True, "score": user.score}


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

    user.score += 1
    user.last_click_at = now
    db.session.commit()

    leaderboard = serialize_leaderboard()
    ws.emit("leaderboard_update", {"leaderboard": leaderboard})
    ws.emit("score_update", {"score": user.score}, to=request.sid)

    return {"ok": True, "score": user.score}


if __name__ == "__main__":
    port = int(environ.get("PORT", 5000))
    ws.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)