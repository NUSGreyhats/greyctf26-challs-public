from flask import Flask, jsonify, request

app = Flask(__name__)
DREAMS = {'n00bcak': 'grey{fake_flag_for_testing}'} # key is same on remote but value is different 
MAX_DREAM_LENGTH = 4096

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
