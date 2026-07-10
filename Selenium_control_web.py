__author__ = "Ives_Wu"
__copyright__ = "Copyright , The PT Project"
__credits__ = 'c270a962b7cb58da4e817c60dd90037f'
__license__ = ""
__version__ = "3.0.1"
__maintainer__ = "Ives_Wu"
__email__ = ["david_yw_lin@pegatroncorp.com",
             "jerry_yf_lin@pegatroncorp.com",
             "Ives_Wu@pegatroncorp.com"]
__status__ = "EVT2.2"



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
from typing import Optional, Callable

# ── Default connection info (fixed for every Ruckus router) ──────────────────
DEFAULT_IP       = "192.168.0.1"
DEFAULT_USER     = "super"
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
        from selenium.webdriver.support.ui import WebDriverWait
        self.wait = WebDriverWait(driver, wait_timeout)
        from selenium.webdriver.common.by import By
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

        # SSL warning
        ssl_indicators = [
            "your connection is not private",
            "not private",
            "certificate error",
            "continue to this website",
            "advanced",  # Chrome SSL detail page
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
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    opts = Options()

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
        from selenium.webdriver.common.keys import Keys
        pw_field.send_keys(Keys.RETURN)

    time.sleep(3)

    # Verify
    state_after = PageState.detect(driver)
    if state_after == PageState.LOGIN_FORM:
        # Login failed — check for error message
        err_el = finder.by_text("invalid", exact=False) or finder.by_text("error", exact=False)
        err_msg = err_el.text if err_el else "Login form still shown — credentials may be wrong"
        raise Exception(err_msg)

    return True


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
    from selenium.webdriver.common.keys import Keys
    body = driver.find_element("tag name", "body")
    body.send_keys(keys_text)
    time.sleep(0.3)
    if press_enter:
        body.send_keys(Keys.RETURN)
        time.sleep(1)
    return True


# ═════════════════════════════════════════════════════════════════════════════
# INFO EXTRACTION
# ═════════════════════════════════════════════════════════════════════════════

def extract_info(driver, fields: list) -> dict:
    """
    Extract device info from current page.
    Supported fields: model, mac, sn (serial), firmware_version, power_type
    Also returns raw page text under "__raw_text" for debugging.
    """
    page = driver.page_source
    info = {}

    # Helper: try list of selectors, return first non-empty result
    def find_first(selectors):
        for s in selectors:
            try:
                if isinstance(s, str) and s.startswith("//"):
                    el = driver.find_element("xpath", s)
                else:
                    el = driver.find_element("css selector", s)
                txt = el.text.strip()
                if txt:
                    return txt
            except Exception:
                pass
        return ""

    # MAC — most common patterns
    if "model" in fields or "mac" in fields or "all" in fields:
        info["mac"] = find_first([
            "[data-testid*='mac']",
            "[data-label*='mac' i]",
            ".mac-address", "[class*='mac-address']",
            "//th[contains(translate(text(),'MAC','mac'),'mac')]/following-sibling::td",
            "//td[contains(translate(text(),'MAC','mac'),'mac')]",
        ])
        if not info.get("mac"):
            m = re.search(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", page)
            if m:
                info["mac"] = m.group(0)

    # Model
    if "model" in fields or "all" in fields:
        info["model"] = find_first([
            "[data-testid*='model']",
            "[data-label*='model' i]",
            ".model-name", "[class*='model-name']",
            "//th[contains(translate(text(),'MODEL','model'),'model')]/following-sibling::td",
            "//td[contains(translate(text(),'MODEL','model'),'model')]",
            "//span[contains(translate(text(),'MODEL','model'),'model')]",
        ])

    # Serial Number
    if "sn" in fields or "serial" in fields or "all" in fields:
        info["sn"] = find_first([
            "[data-testid*='serial']",
            "[data-label*='serial' i]",
            ".serial-number", "[class*='serial-number']",
            "//th[contains(translate(text(),'SERIAL','serial'),'serial')]/following-sibling::td",
            "//td[contains(translate(text(),'SERIAL','serial'),'serial')]",
            "//span[contains(translate(text(),'SERIAL','serial'),'serial')]",
        ])
        if not info.get("sn"):
            m = re.search(r"<td[^>]*>(?:Serial|S/N|S\\/N)[^<]*</td>\s*<td[^>]*>([A-Z0-9]{6,20})</td>", page, re.IGNORECASE)
            if m:
                info["sn"] = m.group(1)

    # Firmware Version
    if "firmware_version" in fields or "firmware" in fields or "all" in fields:
        info["firmware_version"] = find_first([
            "[data-testid*='firmware']", "[data-testid*='version']",
            "[data-label*='firmware' i]", "[data-label*='version' i]",
            "//th[contains(translate(text(),'FIRMWARE','firmware'),'firmware')]/following-sibling::td",
            "//th[contains(translate(text(),'VERSION','version'),'version')]/following-sibling::td",
            "//td[contains(translate(text(),'VERSION','version'),'version')]",
        ])
        if not info.get("firmware_version"):
            m = re.search(r"<td[^>]*>(?:Firmware|Version)[^<]*</td><td[^>]*>([^<]+)</td>", page, re.IGNORECASE)
            if m:
                info["firmware_version"] = m.group(1).strip()

    # Power Type
    if "power_type" in fields or "power" in fields or "all" in fields:
        info["power_type"] = find_first([
            "[data-testid*='power']",
            "[data-label*='power' i]",
            "//th[contains(translate(text(),'POWER','power'),'power')]/following-sibling::td",
            "//th[contains(translate(text(),'POE','poe'),'poe')]/following-sibling::td",
            "//td[contains(translate(text(),'POE','poe'),'poe')]",
            "//td[contains(translate(text(),'POWER','power'),'power')]",
        ])

    # Normalize: empty → N/A
    for k in info:
        if info[k] in ("", "None"):
            info[k] = "N/A"

    # Debug: raw text snippet
    info["_page_title"] = driver.title
    info["_current_url"] = driver.current_url

    return info


def dump_all_values(driver) -> dict:
    """
    Extract ALL visible key-value pairs from the current page (the Device section).
    Looks at HTML tables, definition lists, and label/value component patterns.
    Returns a flat dict {label: value} so C++ can parse and compare freely.
    """
    from selenium.webdriver.common.by import By
    pairs: dict = {}

    def add(k, v):
        k = (k or "").strip().rstrip(":").strip()
        v = (v or "").strip()
        # Keep only sensible label→value pairs
        if not k or not v:
            return
        if len(k) > 60 or "\n" in k:
            return
        if k.lower() == v.lower():
            return
        if k not in pairs:
            pairs[k] = v

    # 1) HTML tables — rows with exactly 2 cells (label, value)
    try:
        for r in driver.find_elements(By.CSS_SELECTOR, "table tr"):
            try:
                cells = r.find_elements(By.XPATH, "./th | ./td")
                if len(cells) == 2:
                    add(cells[0].text, cells[1].text)
            except Exception:
                pass
    except Exception:
        pass

    # 2) Definition lists <dl><dt>label</dt><dd>value</dd>
    try:
        dts = driver.find_elements(By.CSS_SELECTOR, "dl dt")
        dds = driver.find_elements(By.CSS_SELECTOR, "dl dd")
        for dt, dd in zip(dts, dds):
            add(dt.text, dd.text)
    except Exception:
        pass

    # 3) Label/value component patterns (common in React/Ext UIs)
    for label_sel in ["[class*='label']", "[class*='key']", "[class*='name']", "[class*='title']"]:
        try:
            for lab in driver.find_elements(By.CSS_SELECTOR, label_sel):
                try:
                    val = lab.find_element(By.XPATH, "following-sibling::*[1]")
                    add(lab.text, val.text)
                except Exception:
                    pass
        except Exception:
            pass

    # 4) Fallback: "Label : Value" or "Label\tValue" lines in body text
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        for line in body_text.splitlines():
            line = line.strip()
            m = re.match(r"^([A-Za-z][A-Za-z0-9 _/().\-]{1,40})\s*[:：]\s*(.+)$", line)
            if m:
                add(m.group(1), m.group(2))
    except Exception:
        pass

    return pairs


# ═════════════════════════════════════════════════════════════════════════════
# CLI COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

def cmd_login(args) -> None:
    ip = args.ip
    url = f"https://{ip}"

    driver = make_driver(
        args.chromedriver, args.chrome, args.headless,
        args.proxy, args.proxy_user, args.proxy_pass,
    )

    try:
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
    """
    All-in-one: open browser → login (default super/12345678) → click through
    one or more menu levels (e.g. "administrator" "information") → dump ALL
    key-value data as JSON, then quit. Everything in one browser session.

    The menu path is passed on the command line (differs per Ruckus model):
        get_value                        -> default: Device
        get_value Device
        get_value administrator information
    """
    ip = args.ip
    # Menu path = list of items to click in order. Default to [DEFAULT_SECTION].
    path = [s.strip() for s in (getattr(args, "section", None) or []) if s and s.strip()]
    if not path:
        path = [DEFAULT_SECTION]
    driver = None
    try:
        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        finder = ElementFinder(driver, args.timeout)

        # 1) Open + login with default credentials
        driver.get(f"https://{ip}")
        time.sleep(1.5)
        state = PageState.detect(driver)
        print(f"[get_value] Initial page state: {PageState.describe(state)}", file=sys.stderr)
        action_login(driver, ip, args.user, args.password, finder)

        # 2) Click through each menu level in order. Non-fatal per step.
        visited = []
        for item in path:
            try:
                action_navigate(driver, ip, item, finder)
                visited.append(item)
                print(f"[get_value] navigated to: {item}", file=sys.stderr)
            except Exception as e:
                print(f"[get_value] navigate warning at '{item}': {e}", file=sys.stderr)
            time.sleep(1.0)

        # 3) Dump ALL key-value pairs on the final page
        info = dump_all_values(driver)

        # Merge well-known fields (mac/model/sn/firmware/power) for reliability
        specific = extract_info(driver, ["all"])
        for k, v in specific.items():
            if k.startswith("_"):
                continue
            if v and v != "N/A":
                info.setdefault(k, v)

        info["_path"] = " > ".join(path)
        info["_visited"] = " > ".join(visited)
        info["_url"] = driver.current_url
        info["_title"] = driver.title
        info["_count"] = len([k for k in info if not k.startswith("_")])

        out(True, data=info)

    except Exception as e:
        out(False, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


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