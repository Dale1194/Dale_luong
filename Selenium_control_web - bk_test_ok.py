__author__ = "Dale_Luong"
__license__ = ""
__version__ = "0.0.1"
__maintainer__ = "Dale_Luong"
__email__ = ["Dale_Luong@pegatroncorp.com"]
__status__ = "DEMO"



"""
Release Note:
*1.0.0  20260610 Dale_Luong

--------------------------------------

R575 FFC Web Control CLI — Refactored

Design principles:
  1. Detect current page STATE before acting (not assumptions)
  2. All element lookups are retryable with multiple fallback selectors
  3. Default IP/user/password are fixed for every Ruckus router (see constants)
  4. get_value is all-in-one: login + open section + dump ALL data in ONE run

Quick usage (C++ only needs this):
    python Selenium_control_web.py get_value                       -> login + open Device + dump all
    python Selenium_control_web.py get_value Device                -> same, section explicit
    python Selenium_control_web.py get_value administrator information -> click through 2 menu levels
    python Selenium_control_web.py get_value WLAN                  -> read another section

Advanced subcommands (optional, defaults apply):
    python Selenium_control_web.py login [--user <u> --password <p>] [--click-after <text>]
    python Selenium_control_web.py navigate --target <name_or_text>
    python Selenium_control_web.py click --text <text> | --xpath <xpath> | --css <css>
    python Selenium_control_web.py send_keys --text <keys> [--enter]
    python Selenium_control_web.py snapshot [--text-only]
    python Selenium_control_web.py logout

Defaults: IP=192.168.0.1  user=super  password=12345678  section=Device
"""

import argparse
import json
import os
import sys
import time
import re
import base64
from datetime import datetime
from typing import Optional, Callable
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

# ── Default connection info (fixed for every Ruckus router) ──────────────────
DEFAULT_IP       = "192.168.0.1"
DEFAULT_USER     = "super"
OLD_PASSWORD      = "sp-admin"
DEFAULT_PASSWORD = "12345678"
DEFAULT_SECTION  = "Device"

# ── Session ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(SCRIPT_DIR, ".sessions")

def session_path(ip: str) -> str:
    os.makedirs(SESSION_DIR, exist_ok=True)
    # Replace dots so "192.168.0.1" becomes "192_168_0_1"
    safe_ip = ip.replace(".", "_")
    return os.path.join(SESSION_DIR, f"session_{safe_ip}.json")

def save_session(ip: str, data: dict) -> None:
    with open(session_path(ip), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def load_session(ip: str) -> Optional[dict]:
    path = session_path(ip)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clear_session(ip: str) -> None:
    path = session_path(ip)
    if os.path.exists(path):
        os.remove(path)

def session_ok(session: dict) -> bool:
    return session is not None and bool(session.get("cookies"))

def out(ok: bool, data=None, error: str = "") -> None:
    result = {"status": "OK" if ok else "FAIL"}
    if data:
        result["data"] = data
    if error:
        result["error"] = error
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if ok else 1)


# ═════════════════════════════════════════════════════════════════════════════
# ELEMENT FINDER — the core of flexible Selenium
# ═════════════════════════════════════════════════════════════════════════════
class ElementFinder:
    """
    Multi-strategy element finder with retries.
    Tries selectors in order until one succeeds.
    All methods return WebElement or None.
    """

    def __init__(self, driver, wait_timeout: int = 15):
        self.driver = driver
        self.wait_timeout = wait_timeout
        
        self.wait = WebDriverWait(driver, wait_timeout)
        
        self.By = By

    # ── Internal retry wrapper ──────────────────────────────────────────────
    def _try(self, fn: Callable):
        """Try fn(). Return None on any exception."""
        try:
            return fn()
        except Exception:
            return None

    # ── Find by TEXT (most flexible) ───────────────────────────────────────
    def by_text(self, text: str, exact: bool = False, parent=None) -> Optional[object]:
        """Find element whose text contains or equals `text`."""
        ctx = parent or self.driver
        if exact:
            for sel in [
                lambda: ctx.find_element(self.By.LINK_TEXT, text),
                lambda: ctx.find_element(self.By.XPATH, f".//*[text()='{text}']"),
                lambda: ctx.find_element(self.By.XPATH, f".//button[text()='{text}']"),
                lambda: ctx.find_element(self.By.XPATH, f".//a[text()='{text}']"),
                lambda: ctx.find_element(self.By.XPATH, f".//*[normalize-space(text())='{text.strip()}']"),
            ]:
                el = self._try(sel)
                if el and self._visible(el):
                    return el
        else:
            for sel in [
                lambda: ctx.find_element(self.By.PARTIAL_LINK_TEXT, text),
                lambda: ctx.find_element(self.By.XPATH, f".//*[contains(text(),'{text}')]"),
                lambda: ctx.find_element(self.By.XPATH, f".//button[contains(text(),'{text}')]"),
                lambda: ctx.find_element(self.By.XPATH, f".//a[contains(text(),'{text}')]"),
                lambda: ctx.find_element(self.By.XPATH, f".//*[contains(normalize-space(text()),'{text.strip()}')]"),
                # also try data-label (React)
                lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[data-label*='{text}']"),
                lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[data-testid*='{text}']"),
                lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[aria-label*='{text}']"),
                lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[title*='{text}']"),
            ]:
                el = self._try(sel)
                if el and self._visible(el):
                    return el
        return None

    # ── Find by CSS ─────────────────────────────────────────────────────────
    def by_css(self, css: str, parent=None) -> Optional[object]:
        ctx = parent or self.driver
        el = self._try(lambda: ctx.find_element(self.By.CSS_SELECTOR, css))
        if el and self._visible(el):
            return el
        return None

    # ── Find by XPath ───────────────────────────────────────────────────────
    def by_xpath(self, xpath: str, parent=None) -> Optional[object]:
        ctx = parent or self.driver
        el = self._try(lambda: ctx.find_element(self.By.XPATH, xpath))
        if el and self._visible(el):
            return el
        return None

    # ── Find ALL by text ────────────────────────────────────────────────────
    def all_by_text(self, text: str, parent=None) -> list:
        ctx = parent or self.driver
        results = []
        for sel in [
            lambda: ctx.find_elements(self.By.PARTIAL_LINK_TEXT, text),
            lambda: ctx.find_elements(self.By.XPATH, f".//*[contains(text(),'{text}')]"),
            lambda: ctx.find_elements(self.By.CSS_SELECTOR, f"[data-label*='{text}']"),
            lambda: ctx.find_elements(self.By.CSS_SELECTOR, f"[aria-label*='{text}']"),
        ]:
            els = self._try(sel) or []
            results.extend([e for e in els if self._visible(e)])
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for e in results:
            try:
                eid = e.id
            except Exception:
                eid = str(e)
            if eid not in seen:
                seen.add(eid)
                unique.append(e)
        return unique

    # ── Find ALL by CSS ─────────────────────────────────────────────────────
    def all_by_css(self, css: str, parent=None) -> list:
        ctx = parent or self.driver
        els = self._try(lambda: ctx.find_elements(self.By.CSS_SELECTOR, css)) or []
        return [e for e in els if self._visible(e)]

    # ── Find input field by name/type/placeholder ──────────────────────────
    def input_field(self, hint: str = "") -> Optional[object]:
        """Find <input> matching hint in name, type, placeholder, aria-label, or id."""
        inputs = self.all_by_css("input")
        if not hint:
            # Return first editable input
            for inp in inputs:
                t = inp.get_attribute("type") or ""
                if t not in ("hidden", "submit", "button", "reset", "image"):
                    return inp
            return inputs[0] if inputs else None
        hint_lower = hint.lower()
        for inp in inputs:
            attrs = [
                inp.get_attribute("name") or "",
                inp.get_attribute("type") or "",
                inp.get_attribute("placeholder") or "",
                inp.get_attribute("id") or "",
                inp.get_attribute("aria-label") or "",
                inp.get_attribute("class") or "",
            ]
            if any(hint_lower in a.lower() for a in attrs):
                return inp
        # fallback: try XPath by input[@type]
        for t in ["text", "email", "tel"]:
            el = self.by_xpath(f"//input[@type='{t}']")
            if el:
                return el
        return None

    # ── Visibility check ────────────────────────────────────────────────────
    def _visible(self, el) -> bool:
        try:
            return el.is_displayed() and el.is_enabled()
        except Exception:
            return False

    # ── Click with retry ────────────────────────────────────────────────────
    def click(self, el) -> bool:
        try:
            el.click()
            return True
        except Exception:
            pass
        # Try JS click as fallback
        try:
            self.driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False

    # ── Scroll into view then click ────────────────────────────────────────
    def scroll_click(self, el) -> bool:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            return self.click(el)
        except Exception:
            return False


# ═════════════════════════════════════════════════════════════════════════════
# PAGE STATE DETECTOR
# ═════════════════════════════════════════════════════════════════════════════
class PageState:
    """Detect what kind of page is currently displayed."""

    SSL_ADVANCED   = "ssl_advanced"    # Chrome SSL warning: "Not Private / Advanced"
    LOGIN_FORM     = "login_form"      # Username/password form
    DASHBOARD      = "dashboard"       # Already logged in, dashboard/home
    SETUP_WIZARD   = "setup_wizard"    # First-time setup flow
    REDIRECT_LOOP  = "redirect_loop"   # Too many redirects
    UNKNOWN        = "unknown"

    @classmethod
    def detect(cls, driver) -> str:
        url = driver.current_url.lower()
        body = driver.page_source.lower()

        # SSL warning — use only specific markers to avoid false positives
        # (words like "advanced" appear on normal dashboards too)
        ssl_indicators = [
            "your connection is not private",
            "net::err_cert",
            "continue to this website",
            "details-button",
            "proceed-link",
        ]
        if any(ind in body for ind in ssl_indicators):
            return cls.SSL_ADVANCED

        # Login form indicators
        login_indicators = [
            "username", "password",
            "sign in", "signin", "login",
            "登入", "登录",
            "input[type='password']",
        ]
        pw_fields = driver.find_elements("css selector", "input[type='password'], input[name='password']")
        has_pw_field = len(pw_fields) > 0
        has_user = "user" in body or "username" in body

        if has_pw_field and has_user:
            return cls.LOGIN_FORM

        if any(ind in body for ind in login_indicators) and has_user:
            return cls.LOGIN_FORM

        # Setup wizard (no password field yet, but country/language selector)
        setup_indicators = [
            "country", "select country", "select your country",
            "setup", "wizard", "get started",
            "license", "agree",
        ]
        if any(ind in body for ind in setup_indicators):
            # If it also has username fields, it's still setup wizard
            return cls.SETUP_WIZARD

        # Dashboard — logged in (no login form, has nav or main content)
        nav_indicators = [
            "<nav", "class=", "dashboard", "device", "monitor",
            "logout", "sign out",
        ]
        if not has_pw_field and any(ind in body for ind in nav_indicators):
            return cls.DASHBOARD

        # If URL is login/auth but no form detected
        if any(k in url for k in ["login", "signin", "auth", "登入", "登录"]):
            return cls.LOGIN_FORM

        return cls.UNKNOWN

    @classmethod
    def describe(cls, state: str) -> str:
        names = {
            cls.SSL_ADVANCED:  "Chrome SSL Warning (Advanced → Continue)",
            cls.LOGIN_FORM:    "Login Form (username + password)",
            cls.DASHBOARD:     "Dashboard (already logged in)",
            cls.SETUP_WIZARD:  "First-time Setup Wizard",
            cls.REDIRECT_LOOP: "Redirect Loop (possible error)",
            cls.UNKNOWN:       "Unknown page — may need inspection",
        }
        return names.get(state, state)


# ═════════════════════════════════════════════════════════════════════════════
# CHROME DRIVER FACTORY
# ═════════════════════════════════════════════════════════════════════════════
def make_driver(chromedriver: str = "", chrome: str = "", headless: bool = False,
                proxy: str = "", proxy_user: str = "", proxy_pass: str = ""):


    opts = Options()

    # ── Bundled portable Chrome + chromedriver (copied into the project) ──────
    # Neu khong truyen --chrome / --chromedriver thi dung ban di kem trong project.
    # Tranh Selenium Manager phai tai chromedriver qua mang (bi chan -> treo).
    if not chrome:
        bundled_chrome = os.path.join(SCRIPT_DIR, "chrome_win", "chrome.exe")
        if os.path.exists(bundled_chrome):
            chrome = bundled_chrome
    if not chromedriver:
        bundled_driver = os.path.join(SCRIPT_DIR, "chromedriver_win", "chromedriver.exe")
        if os.path.exists(bundled_driver):
            chromedriver = bundled_driver

    # Binary
    if chrome:
        opts.binary_location = chrome

    # SSL / certs
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--ignore-ssl-errors")

    # Stability
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")

    # Keep Chrome running normally when minimized/background
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-ipc-flooding-protection")
    # CRITICAL (Windows): stop Chrome pausing the renderer/compositor when the
    # window is minimized or fully covered. Without this, Selenium calls freeze
    # at the current step until the window is restored.
    opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
    opts.add_argument("--force-color-profile=srgb")
    
    # Proxy (if provided)
    if proxy:
        if proxy_user and proxy_pass:
            manifest_json = '{"name":"ProxyAuth","version":"1.0","permissions":["Proxy"],"obj":\
{"type":"profile","name":"ProxyTemp","single_session":false,"autoLogin":false,"isPAC":false,\
"autodetect":false,"user_settings":"","proxy":{"proxy":"direct"},"single_session":false}}'
            plugin_file = os.path.join(SESSION_DIR, "proxy_auth_plugin.zip")
            os.makedirs(SESSION_DIR, exist_ok=True)
            try:
                import zipfile
                with zipfile.ZipFile(plugin_file, "w") as zf:
                    zf.writestr("manifest.json", manifest_json)
                    background_js = '''
var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: {
            scheme: "http",
            host: "%s",
            port: %s,
            bypassList: []
        },
        bypassList: []
    }
};
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
function callbackFn(details) {
    return {
        authCredentials: { username: "%s", password: "%s" }
    };
}
chrome.webRequest.onAuthRequired.addListener(callbackFn, {urls: ["<all_urls>"]}, ["asyncBlocking"] );
''' % (proxy.split(":")[0], proxy.split(":")[1] if ":" in proxy else "80",
       proxy_user, proxy_pass)
                    zf.writestr("background.js", background_js)
                opts.add_extension(plugin_file)
            except Exception:
                opts.add_argument(f"--proxy-server={proxy}")
        else:
            opts.add_argument(f"--proxy-server={proxy}")

    # Headless
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    if not headless:
        opts.add_argument("--start-maximized")
    
    opts.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"]
    )

    opts.add_experimental_option(
        "useAutomationExtension",
        False
    )
    
    # Load service
    svc = Service(chromedriver) if chromedriver else Service()

    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(2)
    return driver


def restore_session(driver, session: dict, ip: str) -> None:
    """Re-apply saved cookies and navigate to saved URL."""
    driver.get(f"https://{ip}")
    time.sleep(1)
    for cookie in session.get("cookies", []):
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    driver.get(session.get("url", f"https://{ip}"))
    time.sleep(1.5)


def extract_cookies(driver) -> list:
    return driver.get_cookies()


def save_current_session(driver, ip: str) -> dict:
    return {
        "url": driver.current_url,
        "cookies": extract_cookies(driver),
        "ip": ip,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

def switch_to_main_frame(driver, timeout=10):
    """
    Switch to the frame containing the main page content.
    Supports old Ruckus firmware using FRAMESET.
    """

    driver.switch_to.default_content()

    WebDriverWait(driver, timeout).until(
        lambda d: len(d.find_elements(By.TAG_NAME, "frame")) > 0
    )

    # Try common frame names
    for name in [
        "mainframe",
        "mainFrame",
        "main",
        "content",
        "contentframe",
    ]:
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(name)
            return True
        except Exception:
            pass

    # Search by frame src
    driver.switch_to.default_content()

    frames = driver.find_elements(By.TAG_NAME, "frame")

    for f in frames:
        try:
            src = (f.get_attribute("src") or "").lower()

            if (
                "device.asp" in src
                or "status" in src
                or "main" in src
            ):
                driver.switch_to.frame(f)
                return True

        except Exception:
            pass

    return False


# ═════════════════════════════════════════════════════════════════════════════
# PAGE ACTION HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def action_bypass_ssl(driver, ip: str, finder: ElementFinder) -> bool:
    """Handle Chrome SSL warning: click Advanced → Continue."""
    url = f"https://{ip}"
    driver.get(url)
    time.sleep(1.5)

    state = PageState.detect(driver)
    if state != PageState.SSL_ADVANCED:
        return True  # No SSL warning — proceed

    # Step 1: click "Advanced" / "Advanced (not recommended)"
    clicked = False
    for txt in ["Advanced", " advanced"]:
        el = finder.by_text(txt)
        if el:
            finder.scroll_click(el)
            clicked = True
            break

    if not clicked:
        # Try Chrome's specific ID
        el = finder.by_css("#details-button")
        if el:
            finder.scroll_click(el)
            clicked = True

    if not clicked:
        return False  # Can't bypass SSL

    time.sleep(1)

    # Step 2: click "Continue to <ip> (unsafe)" / "Proceed to..."
    for txt in ["Continue to", "Proceed to", "continue to this website"]:
        el = finder.by_text(txt)
        if el:
            finder.scroll_click(el)
            break

    time.sleep(1.5)
    return True


def action_login(driver, ip: str, user: str, password: str, finder: ElementFinder) -> bool:
    """
    Detect current page state and act accordingly:

    SSL_ADVANCED  → bypass SSL → detect again
    SETUP_WIZARD  → handle first-time setup (country + license + set password)
    LOGIN_FORM    → fill credentials → submit
    DASHBOARD     → already logged in, do nothing
    """
    state = PageState.detect(driver)

    if state == PageState.SSL_ADVANCED:
        ok = action_bypass_ssl(driver, ip, finder)
        if not ok:
            raise Exception("Cannot bypass SSL warning")
        state = PageState.detect(driver)
        time.sleep(0.5)

    if state == PageState.SETUP_WIZARD:
        # First-time setup: usually country → license agree → set username/password
        _handle_setup_wizard(driver, finder, user, password)
        time.sleep(2)
        state = PageState.detect(driver)

    if state == PageState.DASHBOARD:
        return True  # Already logged in

    if state != PageState.LOGIN_FORM:
        # Try anyway — maybe form is present but state detection missed it
        pass

    # ── Fill login form ──────────────────────────────────────────────────
    user_field = finder.input_field("user")
    pw_field = finder.input_field("password")

    if not user_field:
        raise Exception("Cannot find username field")
    if not pw_field:
        raise Exception("Cannot find password field")

    user_field.clear()
    user_field.send_keys(user)
    time.sleep(0.3)
    pw_field.clear()
    pw_field.send_keys(password)
    time.sleep(0.3)

    # Submit: try button first, then Enter
    submitted = False
    buttons = finder.all_by_css("button, input[type='submit'], input[type='image']")
    for btn in buttons:
        try:
            t = btn.get_attribute("type") or ""
            if t in ("submit", "image", ""):
                if finder.scroll_click(btn):
                    submitted = True
                    break
        except Exception:
            pass

    if not submitted:
        
        pw_field.send_keys(Keys.RETURN)

    time.sleep(3)

    # Verify
    state_after = PageState.detect(driver)
    if state_after == PageState.LOGIN_FORM:
        # Login failed — check for error message
        err_el = finder.by_text("invalid", exact=False) or finder.by_text("error", exact=False)
        err_msg = err_el.text if err_el else "Login form still shown — credentials may be wrong"
        raise Exception(err_msg)
        
    print("URL:", driver.current_url)
    print("Title:", driver.title)
    print("Frames:", len(driver.find_elements("tag name", "frame")))
    print("IFrames:", len(driver.find_elements("tag name", "iframe")))
    print(driver.page_source[:500])

    return True


def _submit_credentials(driver, user: str, password: str, finder: ElementFinder) -> None:
    """Fill username + password into the login form and submit."""
    user_field = finder.input_field("user")
    pw_field = finder.input_field("password")

    if not user_field:
        raise Exception("Cannot find username field")
    if not pw_field:
        raise Exception("Cannot find password field")

    user_field.clear()
    user_field.send_keys(user)
    time.sleep(0.3)
    pw_field.clear()
    pw_field.send_keys(password)
    time.sleep(0.3)

    submitted = False
    for btn in finder.all_by_css("button, input[type='submit'], input[type='image']"):
        try:
            t = btn.get_attribute("type") or ""
            if t in ("submit", "image", ""):
                if finder.scroll_click(btn):
                    submitted = True
                    break
        except Exception:
            pass

    if not submitted:
        pw_field.send_keys(Keys.RETURN)

    time.sleep(3)


def _is_change_password_page(driver) -> bool:
    """
    Detect the "you must change your password" page shown after logging in
    with the factory default password (sp-admin).
    """
    try:
        body = driver.page_source.lower()
    except Exception:
        return False

    pw_count = len(driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))

    keywords = [
        "change password", "change your password", "new password",
        "set password", "current password", "old password",
        "confirm password", "re-enter", "reenter", "retype",
    ]
    has_kw = any(k in body for k in keywords)

    # Change page has change-specific wording; a plain login form does not.
    return has_kw and pw_count >= 1


def _change_password(driver, old_pw: str, new_pw: str, finder: ElementFinder) -> None:
    """
    Fill the change-password form: set the new password to `new_pw`.
    Handles layouts with 1 (new), 2 (new + confirm) or 3 (old + new + confirm)
    password fields.
    """
    pw_fields = [
        f for f in driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if f.is_displayed()
    ]
    if not pw_fields:
        raise Exception("Change-password page: no password fields found")

    old_field = None
    new_fields = []
    for f in pw_fields:
        attrs = " ".join([
            f.get_attribute("name") or "",
            f.get_attribute("id") or "",
            f.get_attribute("placeholder") or "",
            f.get_attribute("aria-label") or "",
        ]).lower()
        if any(k in attrs for k in ["old", "current", "existing", "orig"]):
            old_field = f
        else:
            new_fields.append(f)

    # Fallback: if 3 fields and none tagged as old, assume first is old.
    if old_field is None and len(pw_fields) >= 3:
        old_field = pw_fields[0]
        new_fields = pw_fields[1:]

    if old_field is not None:
        old_field.clear()
        old_field.send_keys(old_pw)
        time.sleep(0.2)

    for f in new_fields:
        f.clear()
        f.send_keys(new_pw)
        time.sleep(0.2)

    # Submit
    submitted = False
    for btn in finder.all_by_css("button, input[type='submit'], input[type='image']"):
        try:
            t = (btn.get_attribute("type") or "").lower()
            if t in ("submit", "image", ""):
                if finder.scroll_click(btn):
                    submitted = True
                    break
        except Exception:
            pass

    if not submitted:
        for txt in ["Apply", "Save", "OK", "Submit", "Change", "Confirm",
                    "确定", "保存", "提交"]:
            el = finder.by_text(txt, exact=False)
            if el and finder.scroll_click(el):
                submitted = True
                break

    if not submitted and new_fields:
        new_fields[-1].send_keys(Keys.RETURN)

    time.sleep(2)


def login_dual_password(driver, ip: str, user: str, finder: ElementFinder) -> str:
    """
    Login handling models that use 2 password types:

      1. Try OLD_PASSWORD (sp-admin) first.
         - If accepted, the device forces a change-password page
           -> set the new password to DEFAULT_PASSWORD.
      2. If OLD_PASSWORD is rejected, login with DEFAULT_PASSWORD.

    Returns a short tag describing how login happened:
      "old_changed" | "old_direct" | "default"
    """
    state = PageState.detect(driver)

    if state == PageState.SSL_ADVANCED:
        if not action_bypass_ssl(driver, ip, finder):
            raise Exception("Cannot bypass SSL warning")
        time.sleep(0.5)
        state = PageState.detect(driver)

    if state == PageState.SETUP_WIZARD:
        _handle_setup_wizard(driver, finder, user, DEFAULT_PASSWORD)
        time.sleep(2)
        state = PageState.detect(driver)

    if state == PageState.DASHBOARD:
        return "already"

    # ── Attempt 1: OLD_PASSWORD (sp-admin) ──────────────────────────────
    print("[LOG] try old_password", file=sys.stderr, flush=True)
    _submit_credentials(driver, user, OLD_PASSWORD, finder)

    # Old password accepted -> device asks to change it
    if _is_change_password_page(driver):
        print("[LOG] old_password accepted -> change to new password",
              file=sys.stderr, flush=True)
        _change_password(driver, OLD_PASSWORD, DEFAULT_PASSWORD, finder)

        # After changing, some models drop back to the login form
        if PageState.detect(driver) == PageState.LOGIN_FORM:
            _submit_credentials(driver, user, DEFAULT_PASSWORD, finder)
        return "old_changed"

    # Old password accepted and logged straight in
    if PageState.detect(driver) == PageState.DASHBOARD:
        print("[LOG] login OK with old_password", file=sys.stderr, flush=True)
        return "old_direct"

    # ── Attempt 2: DEFAULT_PASSWORD ─────────────────────────────────────
    print("[LOG] old_password failed -> try default password",
          file=sys.stderr, flush=True)
    _submit_credentials(driver, user, DEFAULT_PASSWORD, finder)

    if PageState.detect(driver) == PageState.LOGIN_FORM:
        raise Exception("Login failed with both old (sp-admin) and default password")

    return "default"


def _handle_setup_wizard(driver, finder: ElementFinder, user: str, password: str):
    """
    Handle first-time setup flow. Common steps:
      1. Select country → click Next/Continue
      2. Agree license → click Next/Continue
      3. Set username + password (for super admin) → click Apply/Save
    Steps vary by device — try multiple patterns.
    """
    # Try to proceed through wizard pages (max 5 iterations)
    for _ in range(5):
        state = PageState.detect(driver)
        if state == PageState.DASHBOARD or state == PageState.LOGIN_FORM:
            break  # Setup done

        # Pattern 1: Country dropdown
        dropdown = finder.by_css("select") or finder.by_text("United States") or \
                   finder.by_text("Country", exact=False)
        if dropdown:
            try:
                finder.scroll_click(dropdown)
                time.sleep(0.5)
                opt = finder.by_text("United States") or finder.by_text("United")
                if opt:
                    finder.scroll_click(opt)
                    time.sleep(0.3)
            except Exception:
                pass

        # Pattern 2: "I agree" / license checkbox
        agree = finder.by_text("agree", exact=False) or \
                finder.by_css("input[type='checkbox']") or \
                finder.by_text("license", exact=False)
        if agree:
            try:
                finder.scroll_click(agree)
                time.sleep(0.3)
            except Exception:
                pass

        # Pattern 3: Username + password fields (setup admin account)
        u = finder.input_field("user") or finder.input_field("username")
        p = finder.input_field("password")
        if u and p:
            u.clear()
            u.send_keys(user)
            time.sleep(0.2)
            p.clear()
            p.send_keys(password)
            time.sleep(0.2)
            # Try confirm password field
            pw2 = finder.input_field("confirm")
            if pw2:
                pw2.clear()
                pw2.send_keys(password)
                time.sleep(0.2)

        # Pattern 4: "Next" / "Continue" / "Apply" / "Save" / "Submit" button
        for txt in ["Next", "Continue", "Apply", "Save", "Submit", "Proceed",
                    "下一步", "继续", "保存", "提交", "Next >"]:
            btn = finder.by_text(txt, exact=False)
            if btn:
                finder.scroll_click(btn)
                time.sleep(1.5)
                break

        # Fallback: click any enabled button that looks like "Next/Continue"
        buttons = finder.all_by_css("button")
        for btn in buttons:
            try:
                bt = btn.text.strip().lower()
                if bt in ("", "button") or len(bt) > 30:
                    continue
                if any(k in bt for k in ["next", "continu", "apply", "save", "submit", "下一步", "继续", "save"]):
                    if btn.is_enabled() and btn.is_displayed():
                        finder.scroll_click(btn)
                        time.sleep(1.5)
                        break
            except Exception:
                pass

        time.sleep(0.5)


def action_navigate(driver, ip: str, target: str, finder: ElementFinder) -> bool:
    """
    Click a sidebar/main nav item by target name.
    Target can be: sidebar text, data-label, title, URL path, or CSS selector.
    """
    clicked = False

    # Strategy 1: Click by exact/partial text in sidebar
    for txt in [target, target.lower(), target.upper(), target.capitalize()]:
        el = finder.by_text(txt)
        if el:
            finder.scroll_click(el)
            clicked = True
            break

    # Strategy 2: In sidebar containers
    if not clicked:
        for container_sel in [
            "nav", "aside",
            "[class*='sidebar']", "[class*='menu']", "[class*='nav']",
            "[class*='side-nav']", "[class*='SideNav']",
            "[role='navigation']",
            "#sidebar", ".sidebar", ".menu",
            "[data-testid*='sidebar']", "[data-component*='nav']",
        ]:
            try:
                container = driver.find_element("css selector", container_sel)
                for el in finder.all_by_text(target, parent=container):
                    if finder.scroll_click(el):
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                pass

    # Strategy 3: By title / data-label
    if not clicked:
        for sel in [
            f"[title*='{target}']",
            f"[data-label*='{target}']",
            f"[data-testid*='{target}']",
            f"[aria-label*='{target}']",
        ]:
            el = finder.by_css(sel)
            if el and finder.scroll_click(el):
                clicked = True
                break

    # Strategy 4: By URL path
    if not clicked:
        base = f"https://{ip}"
        for path in [f"/{target.lower()}", f"/{target.lower().replace(' ', '-')}",
                     f"/{target.lower().replace(' ', '_')}"]:
            links = finder.all_by_css("a")
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    if path.rstrip("/") in href.rstrip("/"):
                        finder.scroll_click(link)
                        clicked = True
                        break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        raise Exception(f"Cannot find navigation target: '{target}'")

    time.sleep(2)  # Wait for page transition
    return True


def action_click_by(finder: ElementFinder, by: str, value: str) -> bool:
    """Generic click: --click --text foo | --click --xpath //button | --click --css .btn"""
    if by == "text":
        el = finder.by_text(value, exact=False)
    elif by == "xpath":
        el = finder.by_xpath(value)
    elif by == "css":
        el = finder.by_css(value)
    else:
        raise ValueError(f"Unknown --click-by: {by}")

    if not el:
        raise Exception(f"Element not found: {by}='{value}'")

    if not finder.scroll_click(el):
        raise Exception(f"Cannot click element: {by}='{value}'")

    time.sleep(1)
    return True


def action_send_keys(driver, keys_text: str, press_enter: bool, finder: ElementFinder) -> bool:
    """Send keystrokes to focused element or find input first."""
    
    body = driver.find_element("tag name", "body")
    body.send_keys(keys_text)
    time.sleep(0.3)
    if press_enter:
        body.send_keys(Keys.RETURN)
        time.sleep(1)
    return True


# ═════════════════════════════════════════════════════════════════════════════
# CLI COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

def cmd_login(args) -> None:
    ip = args.ip
    url = f"https://{ip}"

    driver = None
    try:
        driver = make_driver(
            args.chromedriver, args.chrome, args.headless,
            args.proxy, args.proxy_user, args.proxy_pass,
        )

        finder = ElementFinder(driver, args.timeout)

        # ── Detect initial state ────────────────────────────────────────────
        driver.get(url)
        time.sleep(1.5)
        state = PageState.detect(driver)
        print(f"[login] Detected page state: {PageState.describe(state)}", file=sys.stderr)

        # ── Login / Setup ───────────────────────────────────────────────────
        action_login(driver, ip, args.user, args.password, finder)

        # ── Post-login: optional click-after ────────────────────────────────
        if args.click_after:
            state = PageState.detect(driver)
            print(f"[login] After-login state: {PageState.describe(state)}", file=sys.stderr)
            action_navigate(driver, ip, args.click_after, finder)

        # ── Save session ─────────────────────────────────────────────────────
        session = save_current_session(driver, ip)
        save_session(ip, session)
        print(f"[login] Session saved. URL: {driver.current_url}", file=sys.stderr)

        out(True, data={
            "state": PageState.detect(driver),
            "url": driver.current_url,
            "title": driver.title,
        })

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def cmd_navigate(args) -> None:
    ip = args.ip
    target = (args.target or "").strip()
    if not target:
        out(False, error="--target is required")

    driver = None
    try:
        session = load_session(ip)
        if not session:
            out(False, error=f"No session for {ip}. Run 'login' first.")

        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        finder = ElementFinder(driver, args.timeout)

        restore_session(driver, session, ip)
        state = PageState.detect(driver)

        if state in (PageState.LOGIN_FORM, PageState.SSL_ADVANCED):
            out(False, error=f"Session invalid — got state: {PageState.describe(state)}. Please login again.")

        action_navigate(driver, ip, target, finder)

        session["url"] = driver.current_url
        save_session(ip, session)

        out(True, data={
            "target": target,
            "url": driver.current_url,
            "title": driver.title,
            "state": PageState.detect(driver),
        })

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def cmd_click(args) -> None:
    ip = args.ip
    driver = None
    try:
        session = load_session(ip)
        if not session:
            out(False, error=f"No session for {ip}. Run 'login' first.")

        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        finder = ElementFinder(driver, args.timeout)

        restore_session(driver, session, ip)
        state = PageState.detect(driver)

        if state in (PageState.LOGIN_FORM, PageState.SSL_ADVANCED):
            out(False, error="Session invalid. Please login again.")

        # Choose click method
        if args.text:
            by, value = "text", args.text
        elif args.xpath:
            by, value = "xpath", args.xpath
        elif args.css:
            by, value = "css", args.css
        else:
            out(False, error="Must provide --text, --xpath, or --css")

        action_click_by(finder, by, value)

        session["url"] = driver.current_url
        save_session(ip, session)

        out(True, data={
            "clicked": f"{by}={value}",
            "url": driver.current_url,
            "title": driver.title,
        })

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def get_mac_address(body):
    """
    Return:
        40B82D0FAE40

    If not found:
        UNKNOWN
    """

    m = re.search(
        r"MAC Address\s*:\s*([0-9A-Fa-f:]{17})",
        body,
        re.IGNORECASE
    )

    if m:
        return m.group(1).replace(":", "")

    return "UNKNOWN"


def save_fullpage_screenshot(driver, filename):
    """
    Chup anh man hinh bang driver.save_screenshot() (chup tu surface -> chay
    duoc CA KHI cua so bi che HOAC minimize).

    Phuong an lai: truoc khi chup, tu noi CHIEU CAO cua so theo chieu cao that
    cua trang de do bi cat phan duoi. KHONG dung CDP captureBeyondViewport /
    setDeviceMetricsOverride vi cac lenh do buoc compositor ve lai toan trang
    -> treo khi minimize.
    """
    orig = None
    try:
        orig = driver.get_window_size()
    except Exception:
        pass

    try:
        # Chieu cao / rong that su cua noi dung trang (frame hien tai)
        total_h = driver.execute_script(
            "return Math.max("
            "  document.body ? document.body.scrollHeight : 0,"
            "  document.documentElement ? document.documentElement.scrollHeight : 0"
            ");"
        )
        total_w = driver.execute_script(
            "return Math.max("
            "  document.body ? document.body.scrollWidth : 0,"
            "  document.documentElement ? document.documentElement.scrollWidth : 0"
            ");"
        )
        total_h = int(total_h or 0)
        total_w = int(total_w or 0)

        if total_h > 0:
            # Gioi han de tranh kich thuoc qua lon
            win_w = max(1200, min(total_w or 1600, 3000))
            win_h = max(800, min(total_h + 160, 10000))  # +160 chua thanh cong cu Chrome
            driver.set_window_size(win_w, win_h)
            time.sleep(0.5)
    except Exception:
        pass

    driver.save_screenshot(filename)

    # Khoi phuc kich thuoc cua so ban dau
    try:
        if orig:
            driver.set_window_size(orig["width"], orig["height"])
    except Exception:
        pass

    return filename


def wait_page_ready(driver, timeout=10):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return document.readyState"
        ) == "complete"
    )


def cmd_send_keys(args) -> None:
    ip = args.ip
    driver = None
    try:
        session = load_session(ip)
        if not session:
            out(False, error=f"No session for {ip}. Run 'login' first.")

        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        finder = ElementFinder(driver, args.timeout)

        restore_session(driver, session, ip)
        action_send_keys(driver, args.text, args.enter, finder)

        session["url"] = driver.current_url
        save_session(ip, session)

        out(True, data={"sent": args.text, "enter": args.enter})

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def cmd_get_value(args) -> None:
    ip = args.ip
    driver = None

    try:
        print("[LOG] START_TEST", file=sys.stderr, flush=True)

        print("[LOG] make_driver (opening Chrome)...", file=sys.stderr, flush=True)

        driver = make_driver(
            args.chromedriver,
            args.chrome,
            args.headless
        )

        print("[LOG] make_driver OK", file=sys.stderr, flush=True)

        finder = ElementFinder(driver, args.timeout)

        #--------------------------------------------------
        # Login
        #--------------------------------------------------
        driver.get(f"https://{ip}")
        time.sleep(1.5)

        print("[get_value] Login...", file=sys.stderr)

        login_dual_password(
            driver,
            ip,
            args.user,
            finder
        )

        print("[LOG] login OK", file=sys.stderr, flush=True)

        time.sleep(2)
        
        print("[get_value] Switch to main frame...", file=sys.stderr)

        if not switch_to_main_frame(driver):
            raise Exception("Cannot switch to main frame")


        #--------------------------------------------------
        # Navigate theo menu path (hỗ trợ nhiều cấp)
        #--------------------------------------------------

        section = [s for s in (args.section or []) if s] or [DEFAULT_SECTION]

        page_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
            )

        # Chỉ bỏ qua navigate nếu đang ở đúng trang Device mặc định
        already_there = (
            len(section) == 1
            and section[0].lower() == DEFAULT_SECTION.lower()
            and "Device Name" in page_text
        )

        if not already_there:

            print(f"[get_value] Navigate menu path: {' > '.join(section)}",
                  file=sys.stderr)

            for item in section:
                try:
                    action_navigate(driver, ip, item, finder)

                    switch_to_main_frame(driver)

                except Exception as e:
                    print(e, file=sys.stderr)

        #--------------------------------------------------
        # Đọc lại text sau khi navigate
        #--------------------------------------------------

        #body = driver.find_element("tag name", "body").text
        
        switch_to_main_frame(driver)

        wait_page_ready(driver)

        
        
        
        body = driver.execute_script("""
        return document.body
            ? document.body.innerText
            : "";
        """)
        
        # ==========================================================
        # Screenshot
        # ==========================================================

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        SCREENSHOT_DIR = os.path.join(
            BASE_DIR,
            "Screenshot"
        )

        os.makedirs(
            SCREENSHOT_DIR,
            exist_ok=True
        )

        mac = get_mac_address(body)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        base_filename = f"{mac}_{timestamp}"

        png_file = os.path.join(
            SCREENSHOT_DIR,
            base_filename + ".png"
        )
        
        json_file = os.path.join(
            SCREENSHOT_DIR,
            base_filename + ".json"
        )

        #driver.get_screenshot_as_file(png_file)
        save_fullpage_screenshot(driver, png_file)
        print(
            f"[get_value] Screenshot: {png_file}",
            file=sys.stderr
        )
        
        print("Frame Body:")
        print(body[:500])
        
        info = {}

        lines = [
            x.strip()
            for x in body.splitlines()
            if x.strip()
        ]

        wanted = [
            "Device Name",
            "Device Location",
            "GPS Coordinates",
            "Power Consumption Mode",
            "MAC Address",
            "Serial Number",
            "Software Version",
            "Uptime",
            "Current Time",
        ]

        for i, line in enumerate(lines):

            for key in wanted:

                if line.startswith(key):

                    value = ""

                    # Tách phần sau dấu :
                    if ":" in line:
                        value = line.split(":", 1)[1].strip()

                    # Chỉ lấy dòng kế tiếp nếu nó KHÔNG phải một key khác
                    if not value and i + 1 < len(lines):

                        next_line = lines[i + 1]

                        is_next_key = any(
                            next_line.startswith(k)
                            for k in wanted
                        )

                        if not is_next_key:
                            value = next_line

                    info[key] = value

        info["_url"]=driver.current_url
        info["_title"]=driver.title
        info["_count"]=len(info)
        info["_screenshot"] = png_file
        
        out(True,data=info)

    except Exception as e:

        import traceback
        traceback.print_exc()
        out(False,error=str(e))

    finally:

        print("[LOG] END_TEST", file=sys.stderr, flush=True)

        if driver:
            driver.quit()


def cmd_snapshot(args) -> None:
    """Dump page source/text for debugging."""
    ip = args.ip
    driver = None
    try:
        session = load_session(ip)
        driver = make_driver(args.chromedriver, args.chrome, False)
        restore_session(driver, session or {}, ip)

        if args.text_only:
            out(True, data={
                "text": driver.find_element("tag name", "body").text,
                "url": driver.current_url,
                "title": driver.title,
            })
        else:
            out(True, data={
                "html": driver.page_source[:10000],  # limit size
                "url": driver.current_url,
                "title": driver.title,
            })

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def cmd_logout(args) -> None:
    clear_session(args.ip)
    out(True, data={"message": f"Session cleared for {args.ip}"})


# ═════════════════════════════════════════════════════════════════════════════
# MAIN CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="Selenium_control_web.py",
        description="R575 FFC Web Control CLI (flexible Selenium)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples (defaults: IP=192.168.0.1 user=super password=12345678):
  python Selenium_control_web.py get_value                 # login + Device + dump ALL
  python Selenium_control_web.py get_value Device          # section explicit
  python Selenium_control_web.py get_value administrator information  # multi-level menu
  python Selenium_control_web.py get_value WLAN            # read another section
  python Selenium_control_web.py get_value --headless      # no visible window
  python Selenium_control_web.py login                     # just login (defaults)
  python Selenium_control_web.py navigate --target WLAN
  python Selenium_control_web.py click --text Device
  python Selenium_control_web.py snapshot --text-only
  python Selenium_control_web.py logout
'''
    )

    # Global args
    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--chromedriver", default="")
    parser.add_argument("--chrome", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout", type=int, default=15)
    # Proxy
    parser.add_argument("--proxy", default="")
    parser.add_argument("--proxy-user", default="")
    parser.add_argument("--proxy-pass", default="")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── login ──────────────────────────────────────────────────────────────
    p = sub.add_parser("login")
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--click-after", default="",
                   help="After login, navigate to this menu item automatically")
    p.set_defaults(func=cmd_login)

    # ── navigate ───────────────────────────────────────────────────────────
    p = sub.add_parser("navigate")
    p.add_argument("--target", required=True)
    p.set_defaults(func=cmd_navigate)

    # ── click ──────────────────────────────────────────────────────────────
    p = sub.add_parser("click")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", default="")
    g.add_argument("--xpath", default="")
    g.add_argument("--css", default="")
    p.set_defaults(func=cmd_click)

    # ── send_keys ──────────────────────────────────────────────────────────
    p = sub.add_parser("send_keys")
    p.add_argument("--text", required=True)
    p.add_argument("--enter", action="store_true")
    p.set_defaults(func=cmd_send_keys)

    # ── get_value ──────────────────────────────────────────────────────────
    p = sub.add_parser("get_value")
    p.add_argument("section", nargs="*", default=[DEFAULT_SECTION],
                   help="Menu path to click in order before reading "
                        "(e.g. 'administrator information'). Default: Device")
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--fields", default="all",
                   help="(optional) limit well-known fields: model,mac,sn,firmware_version,power_type")
    p.set_defaults(func=cmd_get_value)

    # ── snapshot ───────────────────────────────────────────────────────────
    p = sub.add_parser("snapshot")
    p.add_argument("--text-only", action="store_true")
    p.set_defaults(func=cmd_snapshot)

    # ── logout ─────────────────────────────────────────────────────────────
    sub.add_parser("logout").set_defaults(func=cmd_logout)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()