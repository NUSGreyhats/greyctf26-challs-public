import base64
import html
import os
import secrets
import time

import MySQLdb
import MySQLdb.cursors
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

KEY_BYTES = 32

DB_KW = dict(
    host="127.0.0.1",
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ.get("MYSQL_USER", "notes"),
    passwd=os.environ.get("MYSQL_PASSWORD", "notespw"),
    db=os.environ.get("MYSQL_DATABASE", "notes"),
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    MAX_CONTENT_LENGTH=256 * 1024,
)

_SESSIONS: dict[str, dict] = {}


def get_db():
    conn = MySQLdb.connect(charset="big5", cursorclass=MySQLdb.cursors.DictCursor, **DB_KW)
    conn.autocommit(True)
    return conn


def wait_for_db() -> None:
    last_err = None
    for _ in range(60):
        try:
            get_db().close()
            return
        except MySQLdb.OperationalError as exc:
            last_err = exc
            time.sleep(2)
    raise RuntimeError(f"MySQL not reachable: {last_err}")


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text)


def parse_key(key_hex: str) -> bytes | None:
    try:
        key = bytes.fromhex(key_hex)
    except ValueError:
        return None
    return key if len(key) == KEY_BYTES else None


def parse_username(value: str) -> bytes:
    try:
        return base64.b64decode(value)
    except ValueError:
        return b""


def seal(key: bytes, plaintext: str) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce, ciphertext


def open_sealed(key: bytes, nonce: bytes, ciphertext: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def unseal_blob(key: bytes, blob_b64: str) -> bytes:
    raw = base64.b64decode(blob_b64)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None)


def current_user() -> dict | None:
    sid = session.get("sid")
    return _SESSIONS.get(sid) if sid else None


def start_session(username: bytes, key: bytes) -> None:
    sid = secrets.token_urlsafe(32)
    _SESSIONS[sid] = {"username": username, "key": key}
    session["sid"] = sid


def end_session() -> None:
    sid = session.pop("sid", None)
    if sid:
        _SESSIONS.pop(sid, None)


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("note"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = parse_username(request.form.get("username") or "")
        key = parse_key(request.form.get("key") or "")

        if not username or key is None:
            flash("Username and password are required.")
            return render_template("register.html")

        nonce, ciphertext = seal(key, "")

        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, nonce, ciphertext) VALUES (%s, %s, %s)",
                (username, b64e(nonce), b64e(ciphertext)),
            )
            cur.close()
        except MySQLdb.IntegrityError:
            flash("That username is taken.")
            return render_template("register.html")
        finally:
            conn.close()

        start_session(username, key)
        return redirect(url_for("note"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = parse_username(request.form.get("username") or "")
        key = parse_key(request.form.get("key") or "")

        if key is not None and username:
            conn = get_db()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT nonce, ciphertext FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
                cur.close()
            finally:
                conn.close()

            if row is not None:
                try:
                    open_sealed(key, b64d(row["nonce"]), b64d(row["ciphertext"]))
                except InvalidTag:
                    pass
                else:
                    start_session(username, key)
                    return redirect(url_for("note"))

        flash("Invalid username or password.")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/note", methods=["GET"])
def note():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT nonce, ciphertext FROM users WHERE username = %s",
            (user["username"],),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if row is None:
        end_session()
        return redirect(url_for("login"))

    try:
        encoded_body = open_sealed(user["key"], b64d(row["nonce"]), b64d(row["ciphertext"]))
    except InvalidTag:
        end_session()
        return redirect(url_for("login"))

    return render_template(
        "note.html",
        username=user["username"].decode("big5", "replace"),
        note_view=encoded_body,
        note_edit=html.unescape(encoded_body),
    )


@app.route("/note", methods=["POST"])
def save_note():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    key = user["key"]
    try:
        note_text = unseal_blob(key, request.form.get("enc_note", "")).decode("utf-8")
    except (InvalidTag, ValueError):
        flash("Could not save note.")
        return redirect(url_for("note"))

    nonce, ciphertext = seal(key, html.escape(note_text))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET nonce = %s, ciphertext = %s WHERE username = %s",
            (b64e(nonce), b64e(ciphertext), user["username"]),
        )
        cur.close()
    finally:
        conn.close()

    flash("Saved.")
    return redirect(url_for("note"))


@app.route("/logout", methods=["POST"])
def logout():
    end_session()
    return redirect(url_for("login"))


wait_for_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
