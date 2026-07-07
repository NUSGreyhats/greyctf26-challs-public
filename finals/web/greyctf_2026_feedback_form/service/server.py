import re

import requests
from flask import Flask, redirect, render_template, request, send_from_directory

app = Flask(__name__)

LINK_RE = re.compile(r"https?://[^\s<>'\"]+")
MAX_LINKS = 3
NEGATIVE_WORDS = ("bad", "awful", "terrible", "hate", "worst")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/title.png")
def title():
    return send_from_directory(app.root_path, "title.png")


@app.post("/api/feedback")
def feedback():
    text = request.form.get("feedback", "")

    if any(word in text.lower() for word in NEGATIVE_WORDS):
        return "no badmouthing us!", 400

    for link in LINK_RE.findall(text)[:MAX_LINKS]:
        try:
            response = requests.get(
                link.rstrip(".,;)]}"),
                headers={"User-Agent": "link checker"},
                timeout=3,
            )
            if any(word in response.text.lower() for word in NEGATIVE_WORDS):
                return "no badmouthing us!", 400
        except requests.RequestException:
            pass

    try:
        requests.get(
            "https://feedback.nusgreyhats.org", params={"feedback": text}, timeout=3
        )
    except requests.RequestException:
        pass
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
