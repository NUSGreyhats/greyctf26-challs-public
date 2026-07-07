from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

DREAMS = {'n00bcak': 'grey{The fault, dear n00bcak, is not in our stars, but in our compatibility...}'}
MAX_DREAM_LENGTH = 4096
MAX_REQUEST_OVERHEAD = 1024
MAX_CONTENT_LENGTH = MAX_DREAM_LENGTH + MAX_REQUEST_OVERHEAD

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_):
    return jsonify(error="request is too large"), 413

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/dream")
def get_dream():
    user = request.args.get("user", "").strip()
    if not user:
        return jsonify(error="missing user"), 400
    if user not in DREAMS:
        return jsonify(dream=None), 404
    return jsonify(dream=DREAMS[user])

@app.post("/dream")
def create_dream():
    data = request.get_json(silent=True) or {}
    user = str(data.get("user", "")).strip()
    text = str(data.get("text", "")).strip()
    if not user or not text:
        return jsonify(error="user and text are required"), 400
    if len(text) > MAX_DREAM_LENGTH:
        return jsonify(error="dream is too long"), 400
    if user in DREAMS:
        return jsonify(error="dream already exists"), 409
    DREAMS[user] = text
    return jsonify(dream=text), 201

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
