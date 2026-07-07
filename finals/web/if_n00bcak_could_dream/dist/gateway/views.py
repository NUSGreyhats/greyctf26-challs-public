import hashlib, hmac, html, secrets
from urllib.parse import parse_qsl
import requests
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from werkzeug.datastructures import MultiDict

USERS = {'n00bcak':'5e93016612c8b7b7dc02a34d40182ff0$0edfa50c33ee23a2435913e60c8c60f9fd15c6c3f94831fe461cc851d4b68178'} 
CSS = "body{max-width:720px;margin:40px auto;font:16px sans-serif}textarea{width:100%;height:180px}"
MAX_DREAM_LENGTH = 4096

def decode_body(body):
    return MultiDict(parse_qsl(body.decode()))

def page(title, body, request):
    user = request.session.get("user")
    auth = f"Logged in as <b>{html.escape(user)}</b> | <a href='/logout/'>logout</a>" if user else ""
    nav = "<p><a href='/'>home</a> <a href='/dream/'>dream</a> " + auth + "</p>"
    doc = f"<!doctype html><style>{CSS}</style><title>{title}</title>{nav}<h1>{title}</h1>{body}"
    return HttpResponse(doc)

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120000).hex()
    return f"{salt}${digest}"

def password_ok(password, stored):
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120000).hex()
    return hmac.compare_digest(check, digest)

def account_form(action, button):
    return (
        f"<form method='post' action='{action}'>"
        "<p><input name='user' placeholder='user' required></p>"
        "<p><input name='password' type='password' placeholder='password' required></p>"
        f"<p><button>{button}</button></p></form>"
    )

def credentials(request):
    credentials_user = request.POST.get("user", "").strip()
    credentials_pw = request.POST.get("password", "")
    return request.POST.get("user", "").strip(), request.POST.get("password", "")

def home(request):
    if request.session.get("user"):
        return redirect("/dream/")
    body = "<p><a href='/register/'>create account</a> or <a href='/login/'>login</a></p>"
    return page("Dream gateway", body, request)

def register(request):
    error = ""
    if request.method == "POST":
        user, password = credentials(request)
        if not user or not password:
            error = "user and password are required."
        elif user in USERS:
            error = "That user is taken."
        else:
            USERS[user] = hash_password(password)
            request.session["user"] = user
            return redirect("/dream/")
    return page("Register", f"<p>{html.escape(error)}</p>{account_form('/register/', 'Register')}", request)

def login(request):
    error = ""
    if request.method == "POST":
        user, password = credentials(request)
        stored = USERS.get(user)
        if stored and password_ok(password, stored):
            request.session["user"] = user
            return redirect("/dream/")
        error = "Invalid user or password."
    return page("Login", f"<p>{html.escape(error)}</p>{account_form('/login/', 'Login')}", request)

def logout(request):
    request.session.flush()
    return redirect("/")

def save_dream(user, text):
    if len(text) > MAX_DREAM_LENGTH:
        return "Dream is too long."
    try:
        res = requests.post(f"{settings.BACKEND_URL}/dream", json={"user": user, "text": text}, timeout=2)
        return "Dream saved." if res.status_code == 201 else res.json().get("error", "Could not save.")
    except (requests.RequestException, ValueError):
        return "Dream service is unavailable."

def fetch_dream(user):
    try:
        res = requests.get(f"{settings.BACKEND_URL}/dream", params={"user": user}, timeout=2)
        return (res.json().get("dream"), "") if res.status_code == 200 else (None, "")
    except (requests.RequestException, ValueError):
        return None, "Dream service is unavailable."

def dream(request):
    user = request.session.get("user")
    if request.method == 'GET':
        if user:
            text, error = fetch_dream(user)
            if text is not None:
                body = f"<pre>{html.escape(text)}</pre>"
            else:
                form = "<form method='post'><textarea name='text' required></textarea><p><button>Create dream</button></p></form>"
                body = f"{form}"
            return page("Your dream", body, request)
        else:
            return redirect("/login/")
    elif request.method == 'POST':
        if user:
            notice = save_dream(user, request.POST.get("text", "").strip())
            text, error = fetch_dream(user)
            notice = notice or error 
            if text is not None:
                body = f"<p>{html.escape(notice)}</p><pre>{html.escape(text)}</pre>"
            else:
                form = "<form method='post'><textarea name='text' required></textarea><p><button>Create dream</button></p></form>"
                body = f"<p>{html.escape(notice)}</p>{form}"
            return page("Your dream", body, request)
        error = ""
        user, password = credentials(request)
        stored = USERS.get(user)
        if stored and password_ok(password, stored):
            notice = save_dream(user, request.POST.get("text", "").strip())
            try:
                res = requests.get(f"{settings.BACKEND_URL}/dream", params=decode_body(request.body), timeout=2)
                text, error = (res.json().get("dream"), "") if res.status_code == 200 else (None, "")
            except (requests.RequestException, ValueError):
                text, error = (None, "Dream service is unavailable.")  
            notice = notice or error
            if text is not None:
                body = f"<p>{html.escape(notice)}</p><pre>{html.escape(text)}</pre>"
            else:
                form = "<form method='post'><textarea name='text' required></textarea><p><button>Create dream</button></p></form>"
                body = f"<p>{html.escape(notice)}</p>{form}"
            return page("Your dream", body, request)
        error = "Invalid user or password."
        return page("Login", f"<p>{html.escape(error)}</p>{account_form('/login/', 'Login')}", request)
