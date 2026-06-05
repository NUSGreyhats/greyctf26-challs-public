import os
from contextlib import closing

import psycopg2
import requests
from psycopg2 import errors
from flask import Flask, g, jsonify, request, send_from_directory

app = Flask(__name__)
DB_DSN = os.getenv(
    "DB_DSN",
    "dbname=ctf user=app_user password=fa4bc8e2f481cdf134b779eb1770bd317b52feb4b2fdd37ea41954fc0819977e host=db",
)
FRONTEND_DIR = os.path.join(app.root_path, "frontend")
CHALLENGE_FLAG = os.getenv(
    "CHALLENGE_FLAG", "flag{refint_cascade_update_sql_injection}"
)
CTFD_URL = os.getenv("CTFD_URL", "").rstrip("/")
CTFD_RESOLVE_URL = os.getenv("CTFD_RESOLVE_URL", "").rstrip("/")
CTFD_TEAM_TOKEN_PLUGIN_SECRET = os.getenv(
    "CTFD_TEAM_TOKEN_PLUGIN_SECRET",
    os.getenv("TEAM_TOKEN_PLUGIN_SECRET", ""),
)
CTFD_CHALLENGE_ID = os.getenv(
    "CTFD_CHALLENGE_ID",
    os.getenv("TEAM_TOKEN_CHALLENGE_ID", ""),
)
TEAM_TOKEN_GATE_ENABLED = os.getenv("TEAM_TOKEN_GATE_ENABLED", "")
TEAM_TOKEN_RESOLVE_TIMEOUT_SECONDS = float(
    os.getenv("TEAM_TOKEN_RESOLVE_TIMEOUT_SECONDS", "5")
)


def ctfd_resolve_url() -> str:
    if CTFD_RESOLVE_URL:
        return CTFD_RESOLVE_URL
    if CTFD_URL:
        if "/plugins/team-token/api/v1/resolve" in CTFD_URL:
            return CTFD_URL
        return f"{CTFD_URL}/plugins/team-token/api/v1/resolve"
    return ""


def team_token_gate_enabled() -> bool:
    value = TEAM_TOKEN_GATE_ENABLED.lower()
    if value in {"0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    return bool(ctfd_resolve_url() and CTFD_TEAM_TOKEN_PLUGIN_SECRET)


def extract_team_token() -> str:
    token = request.headers.get("X-Team-Token", "")
    if token:
        return token.strip()

    token = request.args.get("team_token") or request.args.get("token") or ""
    if token:
        return token.strip()

    payload = request.get_json(silent=True) or {}
    token = payload.get("team_token") or payload.get("token") or ""
    return token.strip() if isinstance(token, str) else ""


def resolve_team_token(token: str) -> dict:
    response = requests.get(
        ctfd_resolve_url(),
        params={"token": token},
        headers={"Authorization": f"Bearer {CTFD_TEAM_TOKEN_PLUGIN_SECRET}"},
        timeout=TEAM_TOKEN_RESOLVE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


@app.before_request
def require_unsolved_team_token():
    is_api_request = request.path == "/api" or request.path.startswith("/api/")
    if not is_api_request or not team_token_gate_enabled():
        return None

    if not ctfd_resolve_url() or not CTFD_TEAM_TOKEN_PLUGIN_SECRET:
        return (
            jsonify(
                {"status": "error", "message": "Team token gate is not configured."}
            ),
            503,
        )

    token = extract_team_token()
    if not token:
        return (
            jsonify({"status": "error", "message": "Missing team token."}),
            401,
        )

    try:
        result = resolve_team_token(token)
    except requests.RequestException:
        return (
            jsonify({"status": "error", "message": "Could not verify team token."}),
            502,
        )

    if not result.get("valid"):
        return jsonify({"status": "error", "message": "Invalid team token."}), 403

    if "solved" not in result:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Team token resolve response is missing solve status.",
                }
            ),
            502,
        )

    if CTFD_CHALLENGE_ID and str(result.get("challenge_id")) != str(
        CTFD_CHALLENGE_ID
    ):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Team token is for a different challenge.",
                }
            ),
            403,
        )

    if result.get("solved"):
        return (
            jsonify({"status": "error", "message": "Challenge already solved."}),
            403,
        )

    g.team_token = result
    return None


def get_session_token() -> str | None:
    return request.headers.get("X-Session-Token")


def set_session_player(cur, session_token: str) -> int | None:
    cur.execute("SELECT session_player_id(%s);", (session_token,))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return None

    cur.execute("SELECT set_config('app.player_id', %s, true);", (str(row[0]),))
    return row[0]


def fetch_session(cur, session_token: str):
    cur.execute(
        """
        SELECT
            s.session_token,
            s.player_id,
            primary_name.username,
            private_name.username,
            s.username,
            s.session_note,
            p.display_name,
            p.bio
        FROM user_sessions AS s
        JOIN players AS p ON p.player_id = s.player_id
        JOIN player_usernames AS primary_name
            ON primary_name.player_id = p.player_id AND primary_name.is_primary
        JOIN player_usernames AS private_name
            ON private_name.player_id = p.player_id AND private_name.is_private
        WHERE s.session_token = %s;
        """,
        (session_token,),
    )
    row = cur.fetchone()
    if row is None:
        return None

    return {
        "session_token": row[0],
        "player_id": row[1],
        "username": row[2],
        "private_username": row[3],
        "session_username": row[4],
        "session_note": row[5],
        "display_name": row[6],
        "bio": row[7],
    }


def fetch_posts(cur):
    cur.execute(
        """
        SELECT
            post_id,
            body,
            created_at,
            player_id,
            display_name,
            username
        FROM public_feed_posts();
        """
    )

    return [
        {
            "post_id": row[0],
            "body": row[1],
            "created_at": row[2].isoformat(),
            "player_id": row[3],
            "display_name": row[4],
            "username": row[5],
        }
        for row in cur.fetchall()
    ]


def require_profile(cur):
    session_token = get_session_token()
    if not session_token:
        return None, (
            jsonify({"status": "error", "message": "Missing session token."}),
            401,
        )

    player_id = set_session_player(cur, session_token)
    if player_id is None:
        return None, (jsonify({"status": "error", "message": "Unknown session."}), 404)

    profile = fetch_session(cur, session_token)
    if profile is None:
        return None, (jsonify({"status": "error", "message": "Unknown session."}), 404)

    return profile, None


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def frontend(path: str):
    if path.startswith("api/"):
        return jsonify({"status": "error", "message": "Not found"}), 404

    candidate = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(candidate):
        return send_from_directory(FRONTEND_DIR, path)

    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api")
def api_index():
    return jsonify(
        {
            "message": "Welcome to the SeeTeeEffedIn API",
            "endpoints": [
                "POST /api/register",
                "POST /api/login",
                "GET /api/me",
                "POST /api/profile/handles",
                "POST /api/profile/private-rename",
                "GET /api/posts",
                "POST /api/posts",
            ],
        }
    )


@app.route("/api/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}
    public_username = payload.get("public_username", payload.get("username", ""))
    private_username = payload.get("private_username", "")
    password = payload.get("password", "")
    display_name = payload.get("display_name", "") or public_username
    bio = payload.get("bio", "")

    if (
        not isinstance(public_username, str)
        or not public_username
        or len(public_username) > 64
    ):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Public-facing username must be 1-64 characters.",
                }
            ),
            400,
        )
    if (
        not isinstance(private_username, str)
        or not private_username
        or len(private_username) > 64
    ):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Private-facing username must be 1-64 characters.",
                }
            ),
            400,
        )
    if public_username == private_username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Public and private usernames must be different.",
                }
            ),
            400,
        )
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        return (
            jsonify(
                {"status": "error", "message": "Password must be 8-128 characters."}
            ),
            400,
        )
    if not isinstance(display_name, str) or not display_name or len(display_name) > 80:
        return (
            jsonify(
                {"status": "error", "message": "Display name must be 1-80 characters."}
            ),
            400,
        )
    if not isinstance(bio, str) or len(bio) > 240:
        return jsonify({"status": "error", "message": "Bio is too long."}), 400

    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT register_player(%s, %s, %s, %s, %s, %s);",
                        (
                            public_username,
                            private_username,
                            password,
                            display_name,
                            bio,
                            CHALLENGE_FLAG,
                        ),
                    )
                    session_token = cur.fetchone()[0]
                    set_session_player(cur, session_token)
                    profile = fetch_session(cur, session_token)
                    return jsonify(
                        {
                            "status": "success",
                            "data": {
                                "session_token": session_token,
                                "profile": profile,
                            },
                        }
                    )
    except errors.UniqueViolation:
        return jsonify({"status": "error", "message": "Username already exists."}), 409
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    public_username = payload.get("public_username", payload.get("username", ""))
    private_username = payload.get("private_username", "")
    password = payload.get("password", "")

    if (
        not isinstance(public_username, str)
        or not isinstance(private_username, str)
        or not isinstance(password, str)
    ):
        return jsonify({"status": "error", "message": "Invalid login request."}), 400

    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT login_player(%s, %s, %s);",
                        (public_username, private_username, password),
                    )
                    session_token = cur.fetchone()[0]
                    set_session_player(cur, session_token)
                    profile = fetch_session(cur, session_token)
                    return jsonify(
                        {
                            "status": "success",
                            "data": {
                                "session_token": session_token,
                                "profile": profile,
                            },
                        }
                    )
    except psycopg2.Error as exc:
        if "invalid credentials" in str(exc):
            return jsonify({"status": "error", "message": "Invalid credentials."}), 401
        return jsonify({"status": "error", "message": "Database error occurred."}), 500
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


@app.route("/api/me")
def api_me():
    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn, conn.cursor() as cur:
                profile, error_response = require_profile(cur)
                if error_response is not None:
                    return error_response

                return jsonify({"status": "success", "data": profile})
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


def validate_handle(value, label, max_length):
    if not isinstance(value, str) or not value:
        return f"{label} is required."
    if len(value) > max_length:
        return f"{label} is too long."
    return None


@app.route("/api/profile/handles", methods=["POST"])
def update_profile_handles():
    payload = request.get_json(silent=True) or {}
    public_username = payload.get("public_username")
    private_username = payload.get("private_username")

    if public_username is None and private_username is None:
        return (
            jsonify({"status": "error", "message": "No handle changes provided."}),
            400,
        )

    if public_username is not None:
        error = validate_handle(public_username, "Public-facing username", 64)
        if error:
            return jsonify({"status": "error", "message": error}), 400

    if private_username is not None:
        error = validate_handle(private_username, "Private-facing username", 160)
        if error:
            return jsonify({"status": "error", "message": error}), 400

    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn:
                with conn.cursor() as cur:
                    profile, error_response = require_profile(cur)
                    if error_response is not None:
                        return error_response

                    final_public_username = public_username or profile["username"]
                    final_private_username = (
                        private_username or profile["private_username"]
                    )
                    if final_public_username == final_private_username:
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "message": "Public and private usernames must be different.",
                                }
                            ),
                            400,
                        )

                    if public_username is not None:
                        cur.execute(
                            """
                            UPDATE player_usernames
                            SET username = %s
                            WHERE player_id = %s AND is_primary;
                            """,
                            (public_username, profile["player_id"]),
                        )
                        if cur.rowcount != 1:
                            return (
                                jsonify(
                                    {
                                        "status": "error",
                                        "message": "Public handle update failed.",
                                    }
                                ),
                                400,
                            )

                    if private_username is not None:
                        cur.execute(
                            """
                            UPDATE player_usernames
                            SET username = %s
                            WHERE player_id = %s AND is_private;
                            """,
                            (private_username, profile["player_id"]),
                        )
                        if cur.rowcount != 1:
                            return (
                                jsonify(
                                    {
                                        "status": "error",
                                        "message": "Private handle update failed.",
                                    }
                                ),
                                400,
                            )

                    cur.execute(
                        """
                        UPDATE user_sessions
                        SET username = %s
                        WHERE session_token = %s;
                        """,
                        (final_private_username, profile["session_token"]),
                    )

                    set_session_player(cur, profile["session_token"])
                    updated_profile = fetch_session(cur, profile["session_token"])
                    return jsonify({"status": "success", "data": updated_profile})
    except errors.UniqueViolation:
        return jsonify({"status": "error", "message": "Username already exists."}), 409
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


@app.route("/api/profile/private-rename", methods=["POST"])
def rename_private_profile():
    payload = request.get_json(silent=True) or {}
    new_username = payload.get("username", "")

    if not isinstance(new_username, str) or not new_username:
        return jsonify({"status": "error", "message": "Username is required."}), 400
    if len(new_username) > 160:
        return jsonify({"status": "error", "message": "Username is too long."}), 400

    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn:
                with conn.cursor() as cur:
                    profile, error_response = require_profile(cur)
                    if error_response is not None:
                        return error_response

                    cur.execute(
                        """
                        UPDATE player_usernames
                        SET username = %s
                        WHERE player_id = %s AND is_private;
                        """,
                        (new_username, profile["player_id"]),
                    )

                    if cur.rowcount != 1:
                        return (
                            jsonify({"status": "error", "message": "Rename failed."}),
                            400,
                        )

                    set_session_player(cur, profile["session_token"])
                    updated_profile = fetch_session(cur, profile["session_token"])
                    return jsonify({"status": "success", "data": updated_profile})
    except errors.UniqueViolation:
        return jsonify({"status": "error", "message": "Username already exists."}), 409
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


@app.route("/api/posts")
def get_posts():
    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn, conn.cursor() as cur:
                session_token = get_session_token()
                if session_token:
                    set_session_player(cur, session_token)

                return jsonify({"status": "success", "data": fetch_posts(cur)})
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


@app.route("/api/posts", methods=["POST"])
def create_post():
    payload = request.get_json(silent=True) or {}
    body = payload.get("body", "")

    if not isinstance(body, str) or not body.strip():
        return jsonify({"status": "error", "message": "Post body is required."}), 400
    if len(body) > 280:
        return jsonify({"status": "error", "message": "Post body is too long."}), 400

    try:
        with closing(psycopg2.connect(DB_DSN)) as conn:
            with conn:
                with conn.cursor() as cur:
                    profile, error_response = require_profile(cur)
                    if error_response is not None:
                        return error_response

                    cur.execute(
                        """
                        INSERT INTO posts (player_id, body)
                        VALUES (%s, %s)
                        RETURNING post_id;
                        """,
                        (profile["player_id"], body.strip()),
                    )
                    post_id = cur.fetchone()[0]

                    updated_profile = fetch_session(cur, profile["session_token"])
                    posts = fetch_posts(cur)
                    created_post = next(
                        (post for post in posts if post["post_id"] == post_id), None
                    )
                    return jsonify(
                        {
                            "status": "success",
                            "data": {
                                "post": created_post,
                                "posts": posts,
                                "profile": updated_profile,
                            },
                        }
                    )
    except Exception:
        return jsonify({"status": "error", "message": "Database error occurred."}), 500


if __name__ == "__main__":
    print("Starting Web CTF challenge on port 5000...")
    app.run(host="0.0.0.0", port=5000)
