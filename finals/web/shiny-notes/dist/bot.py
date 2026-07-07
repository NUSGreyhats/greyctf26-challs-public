import os
import secrets
import time

from playwright.sync_api import sync_playwright

FLAG = os.environ.get("FLAG", "grey{replace_me}")


def log(msg: str) -> None:
    print(f"[bot] {msg}", flush=True)


def run_cycle(browser) -> None:
    username = "admin_" + secrets.token_hex(8)
    note_text = "admin secret note " + secrets.token_hex(4)

    context = browser.new_context(ignore_https_errors=True)
    try:
        page = context.new_page()

        page.goto("https://127.0.0.1:443/register", wait_until="domcontentloaded")
        secure = page.evaluate(
            "() => !!(window.isSecureContext && window.crypto && window.crypto.subtle)"
        )
        if not secure:
            raise RuntimeError("page is not a secure context; Web Crypto unavailable")

        page.fill("#username", username)
        page.fill("#password", FLAG)
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.click("button[type=submit]")

        page.fill("#note", note_text)
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.get_by_role("button", name="Save").click()

        page.goto("https://127.0.0.1:443/note", wait_until="domcontentloaded")
        read_back = page.locator("#note").input_value()

        ok = read_back == note_text
        log(f"user={username} wrote={note_text!r} read={read_back!r} ok={ok}")
    finally:
        context.close()


def main() -> None:
    log("starting; base=https://127.0.0.1:443 interval=10s")
    with sync_playwright() as p:
        launch_opts = {"args": ["--no-sandbox"]}
        chromium_path = os.environ.get("CHROMIUM_PATH")
        if chromium_path:
            launch_opts["executable_path"] = chromium_path
        browser = p.chromium.launch(**launch_opts)
        try:
            while True:
                try:
                    run_cycle(browser)
                except Exception as exc:
                    log(f"cycle error: {exc}")
                time.sleep(10)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
