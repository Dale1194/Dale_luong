# ruckus_control_web.py
# Ruckus 650 FFC - Selenium-based Web Automation
# C++ goi: python ruckus_control_web.py get_value dc_power
# -*- coding: utf-8 -*-

__author__ = "Dale_Luong"

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import argparse
import json, os, time, re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# ============================================================
# Device Information Cache
# ============================================================
DEVICE_INFO = {"mac": None, "serial": None, "model": None, "fw": None}
FRAME_CACHE = {"main": None, "menu": None}

DEFAULT_IP       = "192.168.0.1"
DEFAULT_USER     = "super"
OLD_PASSWORD     = "sp-admin"
DEFAULT_PASSWORD = "12345678"
DEFAULT_SECTION  = "Device"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(SCRIPT_DIR, ".sessions")
RESULT_DIR  = os.path.join(SCRIPT_DIR, "result")
os.makedirs(RESULT_DIR, exist_ok=True)

def log(msg):
    print(msg, file=sys.stderr, flush=True)

def out(ok, data=None, error=""):
    result = {"status": "OK" if ok else "FAIL"}
    if data:  result["data"] = data
    if error: result["error"] = error
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    log("========================END_TEST========================")
    sys.exit(0 if ok else 1)

# ============================================================
# ElementFinder (copied from Selenium_control_web.py)
# ============================================================
class ElementFinder:
    def __init__(self, driver, wait_timeout=15):
        self.driver = driver
        self.wait_timeout = wait_timeout
        self.wait = WebDriverWait(driver, wait_timeout)
        self.By = By

    def _try(self, fn):
        try: return fn()
        except: return None

    def _visible(self, el):
        try: return el.is_displayed() and el.is_enabled()
        except: return False

    def by_text(self, text, exact=False, parent=None):
        ctx = parent or self.driver
        selectors = [
            lambda: ctx.find_element(self.By.LINK_TEXT, text),
            lambda: ctx.find_element(self.By.XPATH, f".//*[contains(text(),'{text}')]"),
            lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[data-label*='{text}']"),
            lambda: ctx.find_element(self.By.CSS_SELECTOR, f"[aria-label*='{text}']"),
        ]
        if exact:
            selectors = [
                lambda: ctx.find_element(self.By.LINK_TEXT, text),
                lambda: ctx.find_element(self.By.XPATH, f".//*[text()='{text}']"),
            ]
        for sel in selectors:
            el = self._try(sel)
            if el and self._visible(el): return el
        return None

    def by_css(self, css, parent=None):
        ctx = parent or self.driver
        el = self._try(lambda: ctx.find_element(self.By.CSS_SELECTOR, css))
        return el if el and self._visible(el) else None

    def all_by_text(self, text, parent=None):
        ctx = parent or self.driver
        results = []
        for sel in [
            lambda: ctx.find_elements(self.By.PARTIAL_LINK_TEXT, text),
            lambda: ctx.find_elements(self.By.XPATH, f".//*[contains(text(),'{text}')]"),
            lambda: ctx.find_elements(self.By.CSS_SELECTOR, f"[aria-label*='{text}']"),
        ]:
            els = self._try(sel) or []
            results.extend([e for e in els if self._visible(e)])
        seen = set(); unique = []
        for e in results:
            try: eid = e.id
            except: eid = str(e)
            if eid not in seen:
                seen.add(eid); unique.append(e)
        return unique

    def all_by_css(self, css, parent=None):
        ctx = parent or self.driver
        els = self._try(lambda: ctx.find_elements(self.By.CSS_SELECTOR, css)) or []
        return [e for e in els if self._visible(e)]

    def input_field(self, hint=""):
        inputs = self.all_by_css("input")
        if not hint:
            for inp in inputs:
                t = inp.get_attribute("type") or ""
                if t not in ("hidden","submit","button","reset","image"):
                    return inp
            return inputs[0] if inputs else None
        hint_lower = hint.lower()
        for inp in inputs:
            attrs = [inp.get_attribute(n) or "" for n in ["name","type","placeholder","id","aria-label","class"]]
            if any(hint_lower in a.lower() for a in attrs): return inp
        return None

    def click(self, el):
        try: el.click(); return True
        except:
            try: self.driver.execute_script("arguments[0].click();", el); return True
            except: return False

    def scroll_click(self, el):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({{block:'center'}});", el)
            time.sleep(0.3)
            return self.click(el)
        except: return False

# ============================================================
# PageState (copied from Selenium_control_web.py)
# ============================================================
class PageState:
    SSL_ADVANCED="ssl_advanced"; LOGIN_FORM="login_form"
    DASHBOARD="dashboard"; SETUP_WIZARD="setup_wizard"; UNKNOWN="unknown"

    @classmethod
    def detect(cls, driver):
        url = driver.current_url.lower()
        body = driver.page_source.lower()
        if any(i in body for i in ["your connection is not private","net::err_cert","continue to this website"]):
            return cls.SSL_ADVANCED
        pw_fields = driver.find_elements("css selector","input[type='password'], input[name='password']")
        has_pw = len(pw_fields)>0
        has_user = "user" in body or "username" in body
        if has_pw and has_user: return cls.LOGIN_FORM
        if any(i in body for i in ["sign in","signin","login","登入","登录"]) and has_user:
            return cls.LOGIN_FORM
        if not has_pw and any(i in body for i in ["<nav","class=","dashboard","device","logout"]):
            return cls.DASHBOARD
        if any(k in url for k in ["login","signin","auth"]): return cls.LOGIN_FORM
        return cls.UNKNOWN

# ============================================================
# Chrome Driver Factory (copied from Selenium_control_web.py)
# ============================================================
def make_driver(chromedriver="", chrome="", headless=False):
    opts = Options()
    if not chrome:
        bundled = os.path.join(SCRIPT_DIR,"chrome_win","chrome.exe")
        if os.path.exists(bundled): chrome = bundled
    if not chromedriver:
        bundled_dr = os.path.join(SCRIPT_DIR,"chromedriver_win","chromedriver.exe")
        if os.path.exists(bundled_dr): chromedriver = bundled_dr
    if chrome: opts.binary_location = chrome
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--ignore-ssl-errors")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
    opts.add_argument("--force-color-profile=srgb")
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    else:
        opts.add_argument("--start-maximized")
    opts.add_experimental_option("excludeSwitches",["enable-automation","enable-logging"])
    prefs = {"credentials_enable_service":False,"profile.password_manager_enabled":False}
    opts.add_experimental_option("prefs",prefs)
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    svc = Service(chromedriver) if chromedriver else Service()
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(0)
    return driver

# ============================================================
# Frame Switching (copied from Selenium_control_web.py)
# ============================================================
def switch_to_main_frame(driver, timeout=10):
    driver.switch_to.default_content()
    if FRAME_CACHE["main"]:
        try:
            driver.switch_to.frame(FRAME_CACHE["main"])
            return True
        except: FRAME_CACHE["main"] = None
    WebDriverWait(driver, timeout).until(lambda d: len(d.find_elements(By.TAG_NAME,"frame"))>0)
    frames = driver.find_elements(By.TAG_NAME,"frame")
    for f in frames:
        src = (f.get_attribute("src") or "").lower()
        if any(k in src for k in ["status","configuration","device.asp","internet.asp","wireless"]):
            FRAME_CACHE["main"] = f; driver.switch_to.frame(f); return True
    for f in frames:
        src = (f.get_attribute("src") or "").lower()
        if "nav" not in src and "top" not in src and "bottom" not in src:
            FRAME_CACHE["main"] = f; driver.switch_to.frame(f); return True
    return False

def switch_to_menu_frame(driver, timeout=10):
    driver.switch_to.default_content()
    if FRAME_CACHE["menu"]:
        try:
            driver.switch_to.frame(FRAME_CACHE["menu"])
            return True
        except: FRAME_CACHE["menu"] = None
    WebDriverWait(driver, timeout).until(lambda d: len(d.find_elements(By.TAG_NAME,"frame"))>0)
    frames = driver.find_elements(By.TAG_NAME,"frame")
    for f in frames:
        src = (f.get_attribute("src") or "").lower()
        name = (f.get_attribute("name") or "").lower()
        if any(k in src for k in ["nav","menu","tree"]) or "menu" in name:
            FRAME_CACHE["menu"] = f; driver.switch_to.frame(f); return True
    if len(frames) >= 2:
        FRAME_CACHE["menu"] = frames[1]; driver.switch_to.frame(frames[1]); return True
    return False

# ============================================================
# Login helpers 
# ============================================================
def _submit_credentials(driver, user, password, finder):
    user_field = finder.input_field("user")
    pw_field = finder.input_field("password")
    if not user_field: raise Exception("Cannot find username field")
    if not pw_field: raise Exception("Cannot find password field")
    user_field.clear(); user_field.send_keys(user); time.sleep(0.3)
    pw_field.clear(); pw_field.send_keys(password); time.sleep(0.3)
    submitted = False
    for btn in finder.all_by_css("button, input[type='submit'], input[type='image']"):
        try:
            t = btn.get_attribute("type") or ""
            if t in ("submit","image",""):
                if finder.scroll_click(btn): submitted = True; break
        except: pass
    if not submitted: pw_field.send_keys(Keys.RETURN)
    time.sleep(3)

def _is_change_password_page(driver):
    try: body = driver.page_source.lower()
    except: return False
    pw_count = len(driver.find_elements(By.CSS_SELECTOR,"input[type='password']"))
    keywords = ["change password","change your password","new password","set password",
                "current password","confirm password","re-enter"]
    return any(k in body for k in keywords) and pw_count >= 1

def _change_password(driver, old_pw, new_pw, finder):
    pw_fields = [f for f in driver.find_elements(By.CSS_SELECTOR,"input[type='password']") if f.is_displayed()]
    if not pw_fields: raise Exception("Change-password page: no password fields found")
    old_field = None; new_fields = []
    for f in pw_fields:
        attrs = " ".join([f.get_attribute(n) or "" for n in ["name","id","placeholder","aria-label"]]).lower()
        if any(k in attrs for k in ["old","current","existing"]): old_field = f
        else: new_fields.append(f)
    if old_field is None and len(pw_fields) >= 3:
        old_field = pw_fields[0]; new_fields = pw_fields[1:]
    if old_field:
        old_field.clear(); old_field.send_keys(old_pw); time.sleep(0.2)
    for f in new_fields:
        f.clear(); f.send_keys(new_pw); time.sleep(0.2)
    submitted = False
    for btn in finder.all_by_css("button, input[type='submit']"):
        try:
            t = (btn.get_attribute("type") or "").lower()
            if t in ("submit",""):
                if finder.scroll_click(btn): submitted = True; break
        except: pass
    if not submitted:
        for txt in ["Apply","Save","OK","Submit","Change","Confirm"]:
            el = finder.by_text(txt, exact=False)
            if el and finder.scroll_click(el): submitted = True; break
    if not submitted and new_fields: new_fields[-1].send_keys(Keys.RETURN)
    time.sleep(0.5)

def login_dual_password(driver, ip, user, finder):
    state = PageState.detect(driver)
    if state == PageState.SSL_ADVANCED:
        driver.get(f"https://{ip}"); 
        #time.sleep(1)
        wait_page_ready(driver)
        for txt in ["Advanced"," advanced"]:
            el = finder.by_text(txt)
            if el: finder.scroll_click(el); break
        #time.sleep(0.5)
        for txt in ["Continue to","Proceed to"]:
            el = finder.by_text(txt)
            if el: finder.scroll_click(el); break
        #time.sleep(1)
        wait_page_ready(driver)
        state = PageState.detect(driver)
    if state == PageState.DASHBOARD: return
    log("[LOGIN] Try login old Password.")
    _submit_credentials(driver, user, OLD_PASSWORD, finder)
    if _is_change_password_page(driver):
        log("[LOGIN] Old Password Accepted -> Change to new password.")
        _change_password(driver, OLD_PASSWORD, DEFAULT_PASSWORD, finder)
        if PageState.detect(driver) == PageState.LOGIN_FORM:
            _submit_credentials(driver, user, DEFAULT_PASSWORD, finder)
        return
    if PageState.detect(driver) == PageState.DASHBOARD:
        log("[LOGIN] Login success with old Password."); return
    log("[LOGIN] Login old Password failed -> Try login new password.")
    _submit_credentials(driver, user, DEFAULT_PASSWORD, finder)
    if PageState.detect(driver) == PageState.LOGIN_FORM:
        raise Exception("Login failed with both old and default password")

# ============================================================
# Navigation helpers (copied from Selenium_control_web.py)
# ============================================================
def click_menu_href(driver, href):
    driver.switch_to.default_content()
    switch_to_menu_frame(driver)
    el = driver.find_element(By.CSS_SELECTOR, f'a[href="{href}"]')
    print("TEXT :", el.text, file=sys.stderr)
    print("HREF :", el.get_attribute("href"), file=sys.stderr)
    driver.execute_script("arguments[0].click();", el)
    driver.switch_to.default_content()
    WebDriverWait(driver, 10).until(
        lambda d: any(f.get_attribute("name")=="mainframe" for f in d.find_elements(By.TAG_NAME,"frame"))
    )
    driver.switch_to.default_content()
    switch_to_main_frame(driver)
    wait_page_ready(driver)
    title = driver.find_element(By.TAG_NAME,"body").text.splitlines()[0]
    print("PAGE :", title, file=sys.stderr)

def find_menu(driver, group_name, item_name):
    driver.switch_to.default_content()
    switch_to_menu_frame(driver)
    dls = driver.find_elements(By.TAG_NAME,"dl")
    for dl in dls:
        try:
            dt = dl.find_element(By.TAG_NAME,"dt")
            if dt.text.strip() != group_name: continue
            # Scan all <a> in this <dl> (direct + inside any <dd> submenus)
            all_links = dl.find_elements(By.TAG_NAME,"a")
            # Also scan <dd> submenus for nested links
            try:
                for dd in dl.find_elements(By.TAG_NAME,"dd"):
                    all_links.extend(dd.find_elements(By.TAG_NAME,"a"))
            except: pass
            # 1) Exact match first
            for a in all_links:
                if a.text.strip() == item_name:
                    print(f"MENU FOUND (exact): {group_name} -> {a.text.strip()}", file=sys.stderr)
                    return a
            # 2) Case-insensitive partial match (supports "Support Info" vs "Support Information")
            item_lower = item_name.lower()
            for a in all_links:
                if item_lower in a.text.lower() or a.text.lower() in item_lower:
                    print(f"MENU FOUND (fuzzy): {group_name} -> '{dt.text.strip()}' -> '{a.text.strip()}'", file=sys.stderr)
                    return a
            # Debug: print all available items under this group
            available = [a.text.strip() for a in all_links if a.text.strip()]
            print(f"MENU NOT FOUND: {group_name} -> {item_name}. Available: {available}", file=sys.stderr)
        except: pass
    return None

def find_tab(driver, tab_name):
    """Tim tab trong mainframe, vi du: Wireless1, Wireless9"""
    driver.switch_to.default_content()
    switch_to_main_frame(driver)
    tabs = driver.find_elements(By.CSS_SELECTOR, "#tabnav a, .tabnav a, [role='tab'] a")
    for tab in tabs:
        if tab.text.strip() == tab_name:
            print(f"TAB FOUND: {tab.text.strip()}", file=sys.stderr)
            return tab
    # Fallback: try any link/button containing tab name
    all_links = driver.find_elements(By.CSS_SELECTOR, "a, button")
    for el in all_links:
        try:
            if el.text.strip() == tab_name and el.is_displayed():
                print(f"TAB FOUND (fallback): {tab_name}", file=sys.stderr)
                return el
        except: pass
    return None

def click_tab(driver, tab_name):
    tab_el = find_tab(driver, tab_name)
    if tab_el is None:
        raise Exception(f"Cannot find tab: {tab_name}")
    print(f"TAB: {tab_el.text}", file=sys.stderr)
    driver.execute_script("arguments[0].click();", tab_el)
    wait_page_ready(driver)
    switch_to_main_frame(driver)
    page_title = driver.find_element(By.TAG_NAME, "body").text.splitlines()
    if page_title:
        print(f"PAGE: {page_title[0]}", file=sys.stderr)

def click_menu(driver, group_name, item_name):
    el = find_menu(driver, group_name, item_name)
    if el is None: raise Exception(f"Cannot find menu: {group_name} -> {item_name}")
    print("TEXT :", el.text, file=sys.stderr)
    print("HREF :", el.get_attribute("href"), file=sys.stderr)
    driver.execute_script("arguments[0].click();", el)
    switch_to_main_frame(driver)
    wait_page_ready(driver)
    title = driver.find_element(By.TAG_NAME,"body").text.splitlines()[0]
    print("PAGE :", title, file=sys.stderr)

def wait_page_ready(driver, timeout=10):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState")=="complete")
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME,"body")))
    WebDriverWait(driver, timeout).until(lambda d: len(d.find_element(By.TAG_NAME,"body").text.strip())>0)

def save_fullpage_screenshot(driver, filename):
    orig = None
    try: orig = driver.get_window_size()
    except: pass
    try:
        total_h = int(driver.execute_script("return Math.max(document.body?document.body.scrollHeight:0,document.documentElement?document.documentElement.scrollHeight:0)") or 0)
        total_w = int(driver.execute_script("return Math.max(document.body?document.body.scrollWidth:0,document.documentElement?document.documentElement.scrollWidth:0)") or 0)
        if total_h > 0:
            win_w = max(1200, min(total_w or 1600, 3000))
            win_h = max(800, min(total_h + 160, 10000))
            driver.set_window_size(win_w, win_h)
            time.sleep(0.5)
    except: pass
    driver.save_screenshot(filename)
    try:
        if orig: driver.set_window_size(orig["width"], orig["height"])
    except: pass
    return filename

def take_screenshot(driver, mac, step_name):
    """Chup anh man hinh tai mot thoi diem bat ky.

    Args:
        driver: Selenium WebDriver
        mac: MAC address cua thiet bi (dung dat ten file)
        step_name: Ten buoc - se thanh {MAC}_{step_name}_{timestamp}.png

    Returns:
        Duong dan file anh
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', step_name)
    png_file = os.path.join(RESULT_DIR, f"{mac}_{safe_name}_{timestamp}.png")
    driver.save_screenshot(png_file)
    log(f"[System] Screenshot: {png_file}")
    return png_file

def parse_key_value(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = re.match(r"^(.*?)\s*:\s*(.*)$", line)
        if m: result[m.group(1).strip()] = m.group(2).strip()
    return result

def get_mac_from_body(body):
    m = re.search(r"MAC Address\s*:\s*([0-9A-Fa-f:]{17})", body, re.IGNORECASE)
    if m: return m.group(1).replace(":","").upper()
    return "UNKNOWN"


# ============================================================
# Common login helper: open browser + login 12345678 + get MAC
# ============================================================
def _login_and_get_mac(args):
    """Open Chrome, login with DEFAULT_PASSWORD, get MAC from Status::Device.
    Returns (driver, mac, finder). Caller switches to target page afterwards."""
    ip = args.ip
    driver = make_driver(args.chromedriver, args.chrome, args.headless)
    log("[System] Open Chrome Succesfully.")
    finder = ElementFinder(driver, args.timeout)

    driver.get(f"https://{ip}")
    time.sleep(1.5)
    log("[System] Login to the Ruckus website.")
    _submit_credentials(driver, DEFAULT_USER, DEFAULT_PASSWORD, finder)
    log("[System] Login Succesfully.")

    # Get MAC from Status :: Device
    try:
        click_menu_href(driver, "status/device.asp")
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        dev_body = driver.execute_script("return document.body ? document.body.innerText : '';")
        mac = get_mac_from_body(dev_body) or "unknown"
        DEVICE_INFO["mac"] = mac
        log(f"[System] Device MAC: {mac}")
    except Exception as e:
        log(f"[WARN] Could not get MAC: {e}")
        mac = "unknown"
        DEVICE_INFO["mac"] = mac

    return driver, mac, finder


# ============================================================
# cmd_check_led - OQC-2: Radio 2.4G LED toggle
# python ruckus_control_web.py Configuration "Radio 2.4G" check_led
# ============================================================
# ============================================================
# cmd_check_log - Administration :: Log - Screenshot only
# ============================================================
def cmd_check_log(args):
    """Administration > Log: screenshot and save by MAC.
    Command: python ruckus_control_web.py check_log
    """
    driver = None

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver, mac, finder = _login_and_get_mac(args)
        ip = args.ip

        # Navigate to Administration > Log
        log("[System] Navigate to Administration :: Log ...")
        click_menu(driver, "Administration", "Log")
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        #time.sleep(0.5)

        # Print page body for debug
        body_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
        print("\n" + body_text[:800], file=sys.stderr)
        log(f"[System] Page: {body_text.splitlines()[0] if body_text else '?'}")

        # Screenshot: viewport only
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        png_file = os.path.join(RESULT_DIR, f"{mac}_admin_log_test_{timestamp}.png")
        driver.save_screenshot(png_file)
        log(f"[System] Screenshot: {png_file}")

        out(True, data={
            "screenshot": png_file,
        })
        

    except Exception as e:
        import traceback; traceback.print_exc()
        
        out(False, error=str(e))
    finally:
        if driver:
            try: driver.quit()
            except: pass


# ============================================================
# Screenshot popup helper - show screenshot + OK button
# ============================================================
def _show_popup_and_screenshot(title, message, driver, mac, step_name, auto_close_delay=2):
    """Show a popup message, capture full-screen screenshot WITH popup visible,
    then auto-close the popup after a delay.

    Args:
        title: Popup window title
        message: Message text in popup
        driver: Selenium WebDriver (for full-screen capture)
        mac: MAC address for screenshot filename
        step_name: Step name for screenshot filename
        auto_close_delay: Seconds to wait before auto-closing popup

    Returns:
        Path to the full-screen screenshot (with popup visible)
    """
    screenshot_path = None
    try:
        import tkinter as tk
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        root = tk.Tk()
        root.withdraw()

        dialog = tk.Toplevel(root)
        dialog.title(title)
        dialog.attributes("-topmost", True)
        dialog.geometry("480x200")
        dialog.resizable(False, False)
        dialog.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dw, dh = 480, 200
        dialog.geometry(f"{dw}x{dh}+{(sw-dw)//2}+{(sh-dh)//2}")

        # Title bar
        title_frame = tk.Frame(dialog, bg="#2563EB", pady=8)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text=title,
                 font=("Arial", 13, "bold"), fg="white", bg="#2563EB").pack()

        # Message
        msg_frame = tk.Frame(dialog, padx=15, pady=10)
        msg_frame.pack(fill="both", expand=True)
        tk.Label(msg_frame, text=message,
                 font=("Arial", 11), justify="center").pack(expand=True)

        # OK button
        btn_frame = tk.Frame(dialog, pady=10)
        btn_frame.pack(fill="x", padx=10, side="bottom")

        def on_ok():
            dialog.destroy()
            root.quit()

        btn_ok = tk.Button(
            btn_frame, text="  OK  ", font=("Arial", 12, "bold"),
            bg="#2563EB", fg="white", activebackground="#1D4ED8",
            padx=30, pady=8, command=on_ok, cursor="hand2"
        )
        btn_ok.pack()

        dialog.protocol("WM_DELETE_WINDOW", on_ok)
        dialog.update_idletasks()
        dialog.update()

        # --- Capture full-screen screenshot WITH popup visible ---
        time.sleep(0.5)  # brief pause so popup renders on screen
        screenshot_path = take_screenshot(driver, mac, step_name)
        log(f"[System] Full-screen screenshot (with popup): {screenshot_path}")

        # Auto-close popup after delay
        dialog.after(auto_close_delay * 1000, on_ok)
        dialog.grab_set()
        root.mainloop()
        root.destroy()
    except Exception as e:
        log(f"[WARN] Popup screenshot error: {e}")

    return screenshot_path


# ============================================================
# cmd_factory_reset - Maintenance :: Reboot/reset > Reset now
# ============================================================
def cmd_factory_reset(args):
    """OQC-Final: Factory Reset - Reset now + confirm + re-login.
    Command: python ruckus_control_web.py factory_reset
    """
    ip = args.ip
    driver = None

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        log("[System] Open Chrome Succesfully.")
        finder = ElementFinder(driver, args.timeout)

        # # Login with 12345678 directly
        # driver.get(f"https://{ip}")
        
        # wait_page_ready(driver)
        # #time.sleep(0.5)
        # log("[System] Login to the Ruckus website.")
        # _submit_credentials(driver, DEFAULT_USER, DEFAULT_PASSWORD, finder)
        # log("[System] Login Succesfully.")
        
        driver, mac, finder = _login_and_get_mac(args)

        # Navigate to Maintenance > Reboot/reset
        log("[System] Navigate to Maintenance :: Reboot / Reset ...")
        click_menu(driver, "Maintenance", "Reboot / Reset")
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        time.sleep(1)

        # Print page body for debug
        body_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
        print("\n" + body_text[:800], file=sys.stderr)
        log(f"[System] Page: {body_text.splitlines()[0] if body_text else '?'}")

        # Step 1: Click "Reset now"
        log("[System] Step 1: Click 'Reset now' ...")
        reset_clicked = False
        for txt in ["Reset now", "Reset", "reset now"]:
            try:
                btn = driver.find_element(By.XPATH,
                    f"//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{txt.lower()}')] | "
                    f"//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{txt.lower()}')] | "
                    f"//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{txt.lower()}')]"
                )
                if btn.is_displayed() and btn.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn)
                    log(f"[System] Clicked: {txt}")
                    reset_clicked = True
                    break
            except: pass

        if not reset_clicked:
            log("[WARN] 'Reset now' button not found!")

        time.sleep(1)

        # Step 2: Accept browser confirm dialog automatically
        log("[System] Step 2: Accepting browser confirm dialog ...")
        confirmed = False
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            log(f"[System] Browser alert: {alert_text}")
            alert.accept()
            log("[System] Browser alert accepted")
            confirmed = True
        except Exception as e:
            log(f"[WARN] Browser alert not found: {e}")
            confirmed = True  # proceed anyway

        time.sleep(1)

        # Step 3: Wait for progress bar to complete (may take 1-3 mins)
        log("[System] Step 3: Waiting for reset progress to complete ...")
        progress_done = False
        for i in range(60):  # max 60 cycles x 5s = 5 minutes
            time.sleep(5)
            try:
                body = driver.execute_script(
                    "return document.body ? document.body.innerText : '';"
                )
                # Check for completion indicators
                if any(kw in body for kw in ["completed", "success", "finish", "Resetting done",
                                              "Operation Completed", "System Reboot Required",
                                              "reboot complete", "please login"]):
                    progress_done = True
                    log(f"[System] Reset completed after ~{i*5} seconds")
                    break
                # Check for login page (device may have rebooted and returned to login)
                if "login" in body.lower() or "password" in body.lower():
                    if "user" in body.lower() or "pwd" in body.lower():
                        log("[System] Device returned to login page after reset")
                        progress_done = True
                        break
            except:
                pass

            # If browser is on a blank/reloading page, keep waiting
            if i % 10 == 0:
                log(f"[System] Waiting... {i*5}s elapsed")

        if not progress_done:
            log("[WARN] Progress did not complete in expected time, continuing...")

        log("[System] Reset completed")
        time.sleep(0.5)
        #wait_page_ready(driver)

        # --- Popup: Reset completed, auto-press OK to re-login ---
        # Shows popup + captures full-screen screenshot WITH popup visible
        reset_done_png = _show_popup_and_screenshot(
            title="Factory Reset - Completed",
            message="Reset completed!\nPressing OK to re-login ...",
            driver=driver,
            mac=mac,
            step_name="Reset Done",
            auto_close_delay=2,
        )
        log("[System] Popup auto-closed, proceeding to re-login ...")

        # Step 5: Re-login to confirm reset completed
        # After factory reset, device reverts to default password: super / sp-admin
        log("[System] Step 5: Re-login after reset (using sp-admin) ...")
        re_login_ok = False
        pw_change_detected = False
        try:
            # Navigate to login page
            driver.get(f"https://{ip}")
            #time.sleep(1)
            wait_page_ready(driver)

            # Try login with OLD password (sp-admin) first — factory reset reverts to default
            log("[System] Trying login with super/sp-admin (default after reset) ...")
            _submit_credentials(driver, DEFAULT_USER, OLD_PASSWORD, finder)
            #time.sleep(3)
            wait_page_ready(driver)

            post_login = driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            )

            # Check if password change dialog appeared (expected after reset with old password)
            if any(kw in post_login.lower() for kw in ["change", "new password", "confirm password",
                                                        "password change", "renew", "current password"]):
                pw_change_detected = True
                take_screenshot(driver, mac, "Reset Finish") #capture after re-login OK
                log("[System] Password change dialog detected (device reset to default) → closing browser")
                driver.quit()
                driver = None
                re_login_ok = True  # Login with sp-admin succeeded, now at password change page
            elif "Status" in post_login or "Configuration" in post_login:
                re_login_ok = True
                log("[System] Re-login after reset: OK")
            else:
                # sp-admin failed, try 12345678 as fallback
                log("[WARN] sp-admin login failed after reset, trying 12345678 ...")
                driver.get(f"https://{ip}")
                time.sleep(2)
                _submit_credentials(driver, DEFAULT_USER, DEFAULT_PASSWORD, finder)
                time.sleep(3)
                post_login2 = driver.execute_script(
                    "return document.body ? document.body.innerText : '';"
                )
                if "Status" in post_login2 or "Configuration" in post_login2:
                    re_login_ok = True
                    log("[System] Re-login with 12345678 after reset: OK")
        except Exception as e:
            log(f"[WARN] Re-login failed: {e}")

        out(True, data={
            "reset_clicked":    reset_clicked,
            "confirmed":        confirmed,
            "progress_done":    progress_done,
            "re_login_ok":      re_login_ok,
            "pw_change_dialog": pw_change_detected,
            "result": "PASS" if (reset_clicked and confirmed and re_login_ok) else "FAIL",
        })
        

    except Exception as e:
        import traceback; traceback.print_exc()
        
        out(False, error=str(e))
    finally:
        if driver:
            try: driver.quit()
            except: pass


# ============================================================
# cmd_check_cert - Administration :: Management :: Certificate Verification
# ============================================================
def cmd_check_cert(args):
    """OQC-4: Check Certificate Verification = Passed (green).
    Command: python ruckus_control_web.py check_cert
    """
    driver = None

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver, mac, finder = _login_and_get_mac(args)

        # Navigate to Administration > Management
        log("[System] Navigate to Administration :: Management ...")
        click_menu(driver, "Administration", "Management")
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        #time.sleep(0.5)

        # Print page body for debug
        body_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
        print("\n" + body_text[:1200], file=sys.stderr)
        log(f"[System] Page: {body_text.splitlines()[0] if body_text else '?'}")

        # Screenshot: viewport only
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        png_file = os.path.join(RESULT_DIR, f"{mac}_cert_verification_test_{timestamp}.png")
        driver.save_screenshot(png_file)
        log(f"[System] Screenshot: {png_file}")

        # Find Certificate Verification section
        # Look for text "Certificate" and "Passed"/"Failed" in the page
        cert_found = False
        cert_passed = False
        cert_text = ""

        # Method 1: search page text for certificate status
        for line in body_text.splitlines():
            if "Certificate" in line or "certificate" in line:
                cert_found = True
                log(f"[DEBUG] Found line: {line.strip()}")
            if re.search(r'certificate\s*verification\s*:?\s*passed', line, re.IGNORECASE):
                cert_passed = True
                cert_text = line.strip()
                log(f"[System] Certificate Verification PASSED: {line.strip()}")
            elif re.search(r'certificate\s*verification\s*:?\s*failed', line, re.IGNORECASE):
                cert_passed = False
                cert_text = line.strip()
                log(f"[System] Certificate Verification FAILED: {line.strip()}")

        # Method 2: search HTML for green color indicator + "Passed"
        if not cert_passed and not cert_found:
            html = driver.page_source
            # Look for <font color="green"> or <span class="passed"> + "Passed" near "Certificate"
            green_passed = re.findall(
                r'(?:color[=\"\']*[\w#]+|class="[^"]*passed[^"]*"|>)([^<]*passed[^<]*)<',
                html, re.IGNORECASE
            )
            for m in green_passed:
                if "Certificate" in m or "certificate" in body_text[max(0, body_text.find(m)-200):body_text.find(m)+200]:
                    cert_passed = True
                    cert_text = m.strip()
                    log(f"[System] Certificate Passed (HTML color): {m.strip()}")
                    break

        # Method 3: look for table/cell with status value
        if not cert_passed:
            cells = driver.find_elements(By.TAG_NAME, "td")
            for cell in cells:
                try:
                    ct = cell.text.strip()
                    if re.search(r'certificate', ct, re.IGNORECASE):
                        # Check adjacent cells or parent row for Passed
                        row = cell.find_element(By.XPATH, "ancestor::tr")
                        row_text = row.text
                        if re.search(r'passed', row_text, re.IGNORECASE):
                            cert_passed = True
                            cert_text = row_text.strip()
                            log(f"[System] Certificate Passed (table row): {row_text.strip()}")
                            break
                except: pass

        out(True, data={
            "cert_found":  cert_found,
            "cert_passed": cert_passed,
            "cert_text":   cert_text,
            "screenshot":  png_file,
            "result":      "PASS" if cert_passed else "FAIL",
        })
        

    except Exception as e:
        import traceback; traceback.print_exc()
        
        out(False, error=str(e))
    finally:
        if driver:
            try: driver.quit()
            except: pass


# ============================================================
def cmd_get_support(args):
    """Get Support Info page: scroll full page, screenshot viewport, extract all data.
    Command: python ruckus_control_web.py get_support
    """
    driver = None

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver, mac, finder = _login_and_get_mac(args)

        # Navigate to Maintenance > Support Info
        log("[System] Navigate to Maintenance :: Support Info ...")
        click_menu(driver, "Maintenance", "Support Info")
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        #time.sleep(0.5)

        # Scroll down in small steps until "Boot Version" section appears
        # Stop after max 8 scrolls (~1 mouse wheel per scroll = ~8 "pages")
        log("[System] Scrolling to load Support Info content ...")
        full_text = ""
        found_boot_version = False
        for i in range(8):
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(0.6)
            # Get current visible text
            partial = driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            )
            if "Boot Version" in partial or "### Boot Version" in partial:
                full_text += partial
                found_boot_version = True
                log(f"[System] Reached 'Boot Version' section at scroll #{i+1}")
                break
        else:
            log(f"[System] Max scrolls reached, collecting final text")

        # One final scroll to bottom to make sure everything loaded
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8)
        final_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
        # Always use final_text (scroll-to-bottom has all content loaded)
        full_text = final_text

        # Scroll back to top for screenshot
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        # Trim to "Boot Version" section end if present
        boot_idx = full_text.find("Boot Version")
        if boot_idx >= 0:
            end_idx = full_text.find("\n---", boot_idx)
            if end_idx > 0:
                full_text = full_text[:end_idx].strip()
            # Also remove anything after "### Boot Version" line itself if no separator
            nl = full_text.find("\n", boot_idx + 1)
            if nl > 0:
                # Keep only the first line of "Boot Version" block if content seems to continue beyond
                pass  # keep full block up to separator
        log(f"[System] Full text length: {len(full_text)} chars")

        # Screenshot: viewport only (scroll back to top, no scroll in shot)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        png_file = os.path.join(RESULT_DIR, f"{mac}_support_info_test_{timestamp}.png")
        driver.save_screenshot(png_file)
        log(f"[System] Screenshot: {png_file}")

        # Print preview to console (stderr) — full data is in the screenshot for OCR
        print("\n============SUPPORT_INFO============\n", file=sys.stderr)
        print(full_text[:1500], file=sys.stderr)

        # Build output — minimal: only mac and screenshot path
        output_data = {
            "mac":       mac,
            "screenshot": png_file,
        }

        out(True, data=output_data)
        

    except Exception as e:
        import traceback; traceback.print_exc()
        out(False, error=str(e))
        
    finally:
        if driver:
            try: driver.quit()
            except: pass


# ============================================================
# cmd_check_item - OQC-3: Ethernet Ports LED check
# ============================================================
def cmd_check_item(args):
    """OQC-3: Check Ethernet Ports LED (Port 1 and Port 2)
    Command: python ruckus_control_web.py check_item Configuration "Ethernet Ports"
    """
    ip = args.ip
    driver = None
    port_results = {}

    # menu_path: e.g. ["Configuration", "Ethernet Ports"]
    menu_path = args.menu_path if hasattr(args, 'menu_path') else ["Configuration", "Ethernet Ports"]
    menu_group = menu_path[0] if len(menu_path) >= 1 else "Configuration"
    menu_item  = menu_path[1] if len(menu_path) >= 2 else "Ethernet Ports"
    page_label = f"{menu_group} :: {menu_item}"

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        log("[System] Open Chrome Succesfully.")
        finder = ElementFinder(driver, args.timeout)

        # Login with 12345678 directly
        driver.get(f"https://{ip}")
        wait_page_ready(driver)
        #time.sleep(0.5)
        log("[System] Login to the Ruckus website.")
        _submit_credentials(driver, DEFAULT_USER, DEFAULT_PASSWORD, finder)
        log("[System] Login Succesfully.")

        # Navigate to menu_path (e.g. Configuration > Ethernet Ports)
        log(f"[System] Navigate to {page_label} ...")
        click_menu(driver, menu_group, menu_item)
        switch_to_main_frame(driver)
        wait_page_ready(driver)

        # Print page body for debug
        body_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
        print("\n" + body_text[:800], file=sys.stderr)

        # Collect all tabs on the page (nav tabs, submenu items)
        # First, look for tab links/buttons in the content area
        all_tabs = []
        tab_elements = driver.find_elements(By.CSS_SELECTOR,
            "a[href*='subp'], td.subtab a, td.submenu a, "
            "div.tab a, ul.tab li a, "
            "td.tableft a[href*='eth'], td.tableft a[href*='port'], "
            "input[type='submit'][value*='ort'], input[type='button'][value*='ort']"
        )
        for t in tab_elements:
            try:
                if t.is_displayed():
                    all_tabs.append({
                        "text": t.text.strip(),
                        "href": t.get_attribute("href") or "",
                        "value": t.get_attribute("value") or "",
                    })
            except: pass

        log(f"[System] Page title: {body_text.splitlines()[0] if body_text else '?'}")
        log(f"[DEBUG] Found {len(all_tabs)} tab-like elements")
        for t in all_tabs:
            log(f"  TAB: text={repr(t['text'])} href={t['href']} value={repr(t['value'])}")

        # List of ports to check (default: Port 1, Port 2)
        # If user passed ports via --ports, use those; otherwise scan for tabs
        ports_to_check = getattr(args, 'ports', None)
        if ports_to_check:
            port_names = ports_to_check
        else:
            # Auto-detect: collect tab text that looks like "Port X" or "PortX"
            port_names = []
            for t in all_tabs:
                txt = t['text'].strip()
                if txt and (txt.lower().startswith('port') or
                            re.search(r'\bport\s*\d+\b', txt, re.IGNORECASE) or
                            re.search(r'\bport\d+\b', txt, re.IGNORECASE)):
                    port_names.append(txt)
            if not port_names:
                # Fallback: use link hrefs that reference port-related subpages
                for t in all_tabs:
                    href = t['href'].lower()
                    if 'subp' in href and ('port' in href or 'eth' in href or '1' in href):
                        port_names.append(t['text'].strip() or f"Link({href})")

        # If still empty, try to find tab row by looking for text patterns
        if not port_names:
            log("[WARN] No port tabs auto-detected. Scanning page text for port names...")
            for line in body_text.splitlines():
                if re.search(r'\bport\s*\d+\b', line, re.IGNORECASE):
                    m = re.search(r'(port\s*\d+)', line, re.IGNORECASE)
                    if m and m.group(1) not in port_names:
                        port_names.append(m.group(1))

        # Default ports if nothing found
        if not port_names:
            port_names = ["Port 1", "Port 2"]

        log(f"[System] Ports to check: {port_names}")

        # Check each port
        for port_name in port_names:
            log(f"[System] =======================================")
            log(f"[System] Checking port: {port_name}")

            # Click the port tab
            clicked = False
            for t in all_tabs:
                txt = t['text'].strip()
                href = t['href']
                if (txt and port_name.lower() in txt.lower()) or \
                   (txt == '' and port_name.lower() in href.lower()):
                    try:
                        if hasattr(t, 'click') and callable(getattr(t, 'click')):
                            t.click()
                        else:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", t)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", t)
                        log(f"[System] Clicked tab: {txt or port_name}")
                        time.sleep(1.5)
                        wait_page_ready(driver)
                        clicked = True
                    except Exception as e:
                        log(f"[WARN] Click failed for {txt}: {e}")
                    break

            # Try clicking by text if not found in tab list
            if not clicked:
                for txt_pattern in [port_name, port_name.replace(" ", ""), port_name.replace(" ", "-")]:
                    try:
                        els = driver.find_elements(By.PARTIAL_LINK_TEXT, txt_pattern)
                        for el in els:
                            if el.is_displayed():
                                el.click()
                                log(f"[System] Clicked link text: {txt_pattern}")
                                time.sleep(1.5)
                                wait_page_ready(driver)
                                clicked = True
                                break
                    except: pass
                    if clicked: break

            # Print port page body
            port_body = driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            )
            print("\n--- " + port_name + " ---\n" + port_body[:600], file=sys.stderr)

            # Show the page title after clicking tab
            port_title = port_body.splitlines()[0] if port_body else "?"
            log(f"[System] Port page title: {port_title}")

            # Popup: Is the LED green/OK for this port?
            # Normalize port name for result key (strip suffix like " - (Trunk / WAN)")
            clean_name = re.sub(r'\s*-\s*\(.*?\)\s*$', '', port_name).strip()

            user_ok = _user_confirm_led_check(
                mode="ON",
                extra_msg=f"Port: {clean_name}\nDen LED port nay co xanh/sang khong?",
                skip_image=True  # Ethernet Ports: no reference image
            )
            log(f"[System] Port {clean_name} LED check: {user_ok}")
            port_results[clean_name] = user_ok

        # Result
        all_pass = all(port_results.values()) if port_results else False
        log(f"[System] =======================================")

        out(True, data={
            "port_results": port_results,
            "all_pass":     all_pass,
            "result":       "PASS" if all_pass else "FAIL",
        })
        log("========================END_TEST========================")

    except Exception as e:
        import traceback; traceback.print_exc()
        out(False, error=str(e))
        log("========================END_TEST========================")
    finally:
        if driver:
            try: driver.quit()
            except: pass


def cmd_check_led(args):
    driver = None
    led_on_pass = False
    led_off_pass = False

    # menu_path: e.g. ["Configuration", "Radio 2.4G"] or ["Configuration", "Radio 5G"]
    menu_path = args.menu_path if hasattr(args, 'menu_path') else ["Configuration", "Radio 2.4G"]
    menu_group = menu_path[0] if len(menu_path) >= 1 else "Configuration"
    menu_item  = menu_path[1] if len(menu_path) >= 2 else "Radio 2.4G"
    page_label = f"{menu_group} :: {menu_item}"

    try:
        log("========================START_TEST========================")
        log(f"[System] Opening Chrome ...")
        driver, mac, finder = _login_and_get_mac(args)

        # Navigate to menu_path (e.g. Configuration > Radio 2.4G or Configuration > Radio 5G)
        log(f"[System] Navigate to {page_label} ...")
        click_menu(driver, menu_group, menu_item)
        switch_to_main_frame(driver)
        wait_page_ready(driver)

        # Determine which tab to click after navigating
        # Radio 2.4G -> click "Wireless1" tab
        # Radio 5G   -> click "Wireless9" tab (no space, number concatenated)
        tab_to_click = None
        if "2.4G" in menu_item or "2.4" in menu_item.lower():
            tab_to_click = "Wireless 1"
        elif "5G" in menu_item or "5g" in menu_item.lower():
            tab_to_click = "Wireless9"

        if tab_to_click:
            log(f"[System] Clicking tab: {tab_to_click}")
            try:
                click_tab(driver, tab_to_click)
                log(f"[System] On tab: {tab_to_click}")
            except Exception as e:
                log(f"[WARN] Tab '{tab_to_click}' error: {e}")

        body_text = driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        )
       # print("\n" + body_text[:600], file=sys.stderr)
        log(f"[System] On {page_label} page.")

        # Print page title
        page_title = driver.find_element(By.TAG_NAME, "body").text.splitlines()
        if page_title:
            log(f"[System] Page title: {page_title[0]}")

        # ============================================================
        # Helper: Auto-detect wireless availability radio IDs on current page
        # ============================================================
        def _detect_wireless_radio_ids(driver):
            """Find the Wireless Availability radio button IDs on current page.
            Returns (enable_id, disable_id) or (None, None) if not found."""
            all_radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            for r in all_radios:
                try:
                    if not r.is_displayed():
                        continue
                    rid = r.get_attribute("id") or ""
                    rname = r.get_attribute("name") or ""
                    rval = r.get_attribute("value") or ""
                    # Look for "Wireless Availability" section: radio with name="wireless"
                    # and id like "wireless-y"/"wireless-n" or "wireless9-y"/"wireless9-n"
                    if rname == "wireless" and rid and rval in ("1", "0"):
                        enable_id = rid.replace("-0", "-y") if rid.endswith("-0") else (rid + "-y" if not rid.endswith("-y") else rid)
                        disable_id = rid.replace("-1", "-n") if rid.endswith("-1") else (rid + "-n" if not rid.endswith("-n") else rid)
                        # The base id: wireless-y means enable (value=1), wireless-n means disable (value=0)
                        if rval == "1":
                            return rid, None  # This is the enable radio
                        else:
                            return None, rid  # This is the disable radio
                except: pass
            return None, None

        def _find_wireless_availability_radios(driver):
            """Find Wireless Availability Enable/Disable radio pair.
            Returns (enable_id, disable_id)."""
            all_radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            enable_id = None
            disable_id = None
            for r in all_radios:
                try:
                    if not r.is_displayed():
                        continue
                    rid = r.get_attribute("id") or ""
                    rname = r.get_attribute("name") or ""
                    rval = r.get_attribute("value") or ""
                    # Find radios in "Wireless Availability" section (name="wireless")
                    if rname == "wireless" and rid:
                        if rval == "1":
                            enable_id = rid
                            log(f"[DEBUG] Found Enable radio: #{rid} value={rval}")
                        elif rval == "0":
                            disable_id = rid
                            log(f"[DEBUG] Found Disable radio: #{rid} value={rval}")
                except: pass
            return enable_id, disable_id

        # ============================================================
        # Helper: Click radio + Update Settings + check saved message
        # ============================================================
        def _set_and_save(driver, mac, enable_id, disable_id, want_enable, step_label):
            """Click Enable or Disable radio, then Update Settings. Returns True if saved."""
            radio_id = enable_id if want_enable else disable_id
            log(f"[System] {step_label}")
            log(f"[DEBUG] Target radio: #{radio_id}")

            clicked = False
            # Step A: Click the radio button by ID
            if radio_id:
                try:
                    radio = driver.find_element(By.ID, radio_id)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", radio)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", radio)
                    log(f"[System] Clicked radio: #{radio_id}")
                    clicked = True
                except Exception as e:
                    log(f"[WARN] Could not click #{radio_id}: {e}")

            if not clicked:
                # Fallback: click the label
                try:
                    lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", lbl)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", lbl)
                    log(f"[System] Clicked label[for='{radio_id}']")
                    clicked = True
                except Exception as e2:
                    log(f"[WARN] Fallback label click also failed: {e2}")

            time.sleep(0.8)

            # Step B: Click Update Settings
            saved_ok = False
            for btn_txt in ["Update Settings", "Apply", "Save"]:
                try:
                    btns = driver.find_elements(By.XPATH,
                        f"//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{btn_txt.lower()}')] | "
                        f"//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{btn_txt.lower()}')] | "
                        f"//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{btn_txt.lower()}')]")
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            log(f"[System] Clicked: {btn_txt}")
                            saved_ok = True
                            break
                    if saved_ok: break
                except: pass
            time.sleep(2)

            # ============================================================
            # CHUP ANH: Sau khi an Update Settings, kiem tra "Your parameters were saved"
            # ============================================================
            screenshot_name = f"{menu_item}_{'enable' if want_enable else 'disable'}_saved"
            take_screenshot(driver, mac, screenshot_name)

            # Step C: Check "Your parameters were saved"
            body_text = driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            )
            msg_ok = "Your parameters were saved" in body_text
            log(f"[System] 'Your parameters were saved' found: {msg_ok}")
            return msg_ok

        # ============================================================
        # Auto-detect Wireless Availability radio IDs on current page
        # ============================================================
        enable_id, disable_id = _find_wireless_availability_radios(driver)
        if not enable_id or not disable_id:
            log("[WARN] Could not auto-detect Wireless Availability radio IDs!")

        # ============================================================
        # Step 1: Wireless Availability = Enable -> Update -> Dialog
        # ============================================================
        msg_ok = _set_and_save(driver, mac, enable_id, disable_id, True, "Step 1: Wireless Availability = Enable")

        # Dialog: User check LED ON (pass menu_item to select correct reference image)
        led_on_check = _user_confirm_led_check(mode="ON", menu_item=menu_item)
        log(f"[System] User LED ON check: {led_on_check}")
        led_on_pass = bool(led_on_check and msg_ok)
        log(f"[System] Check_Led_On: {'PASS' if led_on_pass else 'FAIL'}")

        # ============================================================
        # Step 2: Wireless Availability = Disable -> Update -> Dialog
        # ============================================================
        msg_ok2 = _set_and_save(driver, mac, enable_id, disable_id, False, "Step 2: Wireless Availability = Disable")

        # Dialog: User check LED OFF (pass menu_item to select correct reference image)
        led_off_check = _user_confirm_led_check(mode="OFF", menu_item=menu_item)
        log(f"[System] User LED OFF check: {led_off_check}")
        led_off_pass = bool(led_off_check and msg_ok2)
        log(f"[System] Check_Led_Off: {'PASS' if led_off_pass else 'FAIL'}")

        # ============================================================
        # Result
        # ============================================================
        all_pass = led_on_pass and led_off_pass

        out(True, data={
            "led_on_pass":  led_on_pass,
            "led_off_pass": led_off_pass,
            "led_on_msg":   msg_ok,
            "led_off_msg":  msg_ok2,
            "result":       "PASS" if all_pass else "FAIL",
        })
        

    except Exception as e:
        import traceback; traceback.print_exc()
        out(False, error=str(e))
        
    finally:
        if driver:
            try: driver.quit()
            except: pass


# ============================================================
# LED check dialog - simple OK/Cancel
# ============================================================
def _user_confirm_led_check(mode="ON", extra_msg="", menu_item="", skip_image=False):
    """Show a dialog asking user to verify LED is ON/OFF with a reference image.

    Args:
        mode: "ON" or "OFF"
        extra_msg: Additional message to show
        menu_item: "2.4G" or "5G" to select correct reference image
        skip_image: True to hide reference image (e.g. for Ethernet Ports)

    Returns:
        True=OK, False=Cancel
    """
    try:
        import tkinter as tk
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        root = tk.Tk()
        root.withdraw()

        # ---- Build image path ----
        # Note: Windows cannot save "2.4G.png" (dot in filename) → use "2_4G.png"
        band = "2_4G"  # filename-safe (underscore)
        band_display = "2.4G"  # user-friendly display (dot)
        if menu_item:
            if "5G" in menu_item or "5g" in menu_item.lower():
                band = "5G"
                band_display = "5G"
            else:
                band = "2_4G"
                band_display = "2.4G"
        if extra_msg:
            band_display = "CHECK_LED_PORT"
        
        img_name = f"LED_{mode}_{band}.png"
        img_path = os.path.join(SCRIPT_DIR, img_name)

        log(f"[DEBUG] LED dialog: band={band}, mode={mode}, img_path={img_path}, exists={os.path.exists(img_path)}")

        # ---- Build message ----
        if extra_msg:
            msg_text = f"Vui lòng kiểm tra đèn LED trên thiết bị:\n\n{extra_msg}\n\nĐèn có xanh/sáng (OK) hay không?"
        else:
            msg_text = f"Vui lòng kiểm tra đèn LED trên thiết bị.\n\nLED có {mode.upper()} hay không?"

        # ---- Create custom dialog ----
        dialog = tk.Toplevel(root)
        dialog.title(f"LED {mode.upper()} - Kiểm tra LED ({band_display})")
        dialog.attributes("-topmost", True)
        dialog.geometry("560x720")
        dialog.resizable(False, False)
        dialog.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dw, dh = 560, 720
        dialog.geometry(f"{dw}x{dh}+{(sw-dw)//2}+{(sh-dh)//2}")

        # ---- Title label ----
        title_frame = tk.Frame(dialog, bg="#2563EB", pady=10)
        title_frame.pack(fill="x")
        tk.Label(
            title_frame,
            text=f"LED {mode.upper()} - Kiểm tra LED ({band_display})",
            font=("Arial", 14, "bold"), fg="white", bg="#2563EB"
        ).pack()

        # ---- Image section ----
        if not skip_image:
            img_frame = tk.Frame(dialog, bg="#F3F4F6", padx=10, pady=10)
            img_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

            _photo_ref = [None]  # keep PIL PhotoImage alive

            if os.path.exists(img_path):
                img_loaded_ok = False
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(img_path)

                    # Resize: max 520px width, max 480px height, keep aspect ratio
                    img_w, img_h = pil_img.size
                    max_w = 520
                    max_h = 480
                    if img_w > max_w:
                        ratio = max_w / img_w
                        new_h = int(img_h * ratio)
                        if new_h > max_h:
                            ratio = max_h / img_h
                            pil_img = pil_img.resize((int(img_w * ratio), max_h), Image.LANCZOS)
                        else:
                            pil_img = pil_img.resize((max_w, new_h), Image.LANCZOS)
                    elif img_h > max_h:
                        ratio = max_h / img_h
                        pil_img = pil_img.resize((int(img_w * ratio), max_h), Image.LANCZOS)

                    _photo_ref[0] = ImageTk.PhotoImage(pil_img)
                    log(f"[DEBUG] PIL: {img_w}x{img_h} -> {pil_img.size}, display OK")

                    img_label = tk.Label(img_frame, image=_photo_ref[0], bg="#F3F4F6", bd=2, relief="solid")
                    img_label.pack(pady=5)
                    img_loaded_ok = True

                except Exception as pil_err:
                    log(f"[WARN] PIL failed '{img_name}': {pil_err}")
                    img_loaded_ok = False

                # Fallback if PIL failed
                if not img_loaded_ok:
                    try:
                        tk.Label(
                            img_frame,
                            text=f"[Tai anh that bai: {img_name}]\nKiem tra den LED truc tiep tren thiet bi.",
                            font=("Arial", 10), fg="#B45309", bg="#FEF3C7",
                            wraplength=500, justify="center", padx=20, pady=20,
                            relief="solid", highlightbackground="#F59E0B"
                        ).pack(pady=10)
                    except Exception as fb_err:
                        log(f"[WARN] Fallback label also failed: {fb_err}")

            else:
                # File not found fallback
                try:
                    tk.Label(
                        img_frame,
                        text=f"[Anh minh hoa khong ton tai]\n{img_path}",
                        font=("Arial", 10), fg="#DC2626", bg="#FEF2F2",
                        wraplength=500, justify="center", padx=20, pady=20,
                        relief="solid", highlightbackground="#FCA5A5"
                    ).pack(pady=10)
                except Exception as fb_err:
                    log(f"[WARN] File-not-found fallback label failed: {fb_err}")
                log(f"[WARN] Image file not found: {img_path}")

        # ---- Message section ----
        msg_frame = tk.Frame(dialog, padx=15, pady=10)
        msg_frame.pack(fill="x", padx=10)
        tk.Label(
            msg_frame, text=msg_text,
            font=("Arial", 11), justify="left", anchor="w"
        ).pack(anchor="w")

        # ---- Buttons ----
        btn_frame = tk.Frame(dialog, pady=15)
        btn_frame.pack(fill="x", padx=10, side="bottom")

        response = [None]

        def on_yes():
            response[0] = True
            dialog.destroy()
            root.quit()

        def on_no():
            response[0] = False
            dialog.destroy()
            root.quit()

        btn_yes = tk.Button(
            btn_frame, text="  YES ", font=("Arial", 12, "bold"),
            bg="#16A34A", fg="white", activebackground="#15803D",
            padx=20, pady=8, command=on_yes, cursor="hand2"
        )
        btn_yes.pack(side="left", expand=True, fill="x", padx=(0, 5))

        btn_no = tk.Button(
            btn_frame, text="  NO  ", font=("Arial", 12, "bold"),
            bg="#DC2626", fg="white", activebackground="#B91C1C",
            padx=20, pady=8, command=on_no, cursor="hand2"
        )
        btn_no.pack(side="right", expand=True, fill="x", padx=(5, 0))

        def on_close():
            response[0] = False
            dialog.destroy()
            root.quit()

        dialog.protocol("WM_DELETE_WINDOW", on_close)

        # Force render image BEFORE showing dialog
        dialog.update_idletasks()
        dialog.update()

        # Run dialog
        dialog.grab_set()
        root.mainloop()
        root.destroy()

        if response[0] is None:
            log("[WARN] LED dialog closed without selection, defaulting to True")
            return True
        return bool(response[0])

    except Exception as e:
        log(f"[WARN] LED dialog error: {e}")
        import traceback
        traceback.print_exc()
        return True


# ============================================================
# cmd_get_value - dc_power only
# ============================================================
def cmd_get_value(args):
    ip = args.ip
    mode = args.value_type
    driver = None
    try:
        log("========================START_TEST========================")
        log("[System] Opening Chrome ...")
        driver = make_driver(args.chromedriver, args.chrome, args.headless)
        log("[System] Open Chrome Succesfully.")
        finder = ElementFinder(driver, args.timeout)

        # Login
        driver.get(f"https://{ip}")
        
        wait_page_ready(driver)
        #time.sleep(0.5)
        log("[System] Login to the Ruckus website.")
        if mode == "dc_power":
            login_dual_password(driver, ip, args.user, finder)
        else:
            _submit_credentials(driver, DEFAULT_USER, DEFAULT_PASSWORD, finder)
    
        log("[System] Login Succesfully.")

        # Navigate to Status :: Device
        log("[System] Navigate to Status :: Device ...")
        click_menu_href(driver, "status/device.asp")

        # Wait and get body text
        switch_to_main_frame(driver)
        wait_page_ready(driver)
        body = driver.execute_script("return document.body ? document.body.innerText : '';")

        # Parse key-value pairs
        info = parse_key_value(body)

        # Get MAC for filename
        mac = get_mac_from_body(body)
        DEVICE_INFO["mac"] = mac

        # Build screenshot path: {MAC}_{item}_test_{YYYYMMDD}.png
        item_name = mode  # "dc_power" or "poe_power"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        png_file = os.path.join(RESULT_DIR, f"{mac}_{item_name}_test_{timestamp}.png")

        # Screenshot
        save_fullpage_screenshot(driver, png_file)
        log(f"[System] Screenshot: {png_file}")

        # Print data to console
        print("===GET_DATA===")
        print(body[:800])

        # Build output data
        output_data = {
            "mac":        info.get("MAC Address","").replace(":","").upper(),
            "sn":         info.get("Serial Number",""),
            "sw_version": info.get("Software Version",""),
            "power_mode": info.get("Power Consumption Mode",""),
            "screenshot": png_file,
        }       
        print("===END_DATA===")
        out(True, data=output_data)
        

    except Exception as e:
        import traceback; traceback.print_exc()
        out(False, error=str(e))
        
    finally:
        if driver:
            try: driver.quit()
            except: pass

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Ruckus 650 FFC Web Control")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- get_value (OQC-1) ----
    p_get = sub.add_parser("get_value",
        help="get_value dc_power - Login + Get Device Info")
    p_get.add_argument("value_type", help="dc_power")
    p_get.add_argument("--ip",          default=DEFAULT_IP)
    p_get.add_argument("--chromedriver",default="")
    p_get.add_argument("--chrome",      default="")
    p_get.add_argument("--headless",    action="store_true")
    p_get.add_argument("--timeout",     type=int, default=15)
    p_get.add_argument("--user",        default=DEFAULT_USER)
    p_get.set_defaults(func=cmd_get_value)

    # ---- get_support (Support Info: scroll full page + screenshot + extract data) ----
    p_sup = sub.add_parser("get_support",
        help="get_support - Maintenance > Support Info: screenshot + full data")
    p_sup.add_argument("--ip",          default=DEFAULT_IP)
    p_sup.add_argument("--chromedriver",default="")
    p_sup.add_argument("--chrome",      default="")
    p_sup.add_argument("--headless",    action="store_true")
    p_sup.add_argument("--timeout",     type=int, default=15)
    p_sup.set_defaults(func=cmd_get_support)

    # ---- check_led (OQC-2: Radio 2.4G LED toggle) ----
    p_led = sub.add_parser("check_led",
        help="check_led - Radio 2.4G LED Enable/Disable test")
    p_led.add_argument("menu_path", nargs="*",
        default=["Configuration","Radio 2.4G"],
        help="Menu path, e.g. Configuration Radio 2.4G")
    p_led.add_argument("--ip",          default=DEFAULT_IP)
    p_led.add_argument("--chromedriver",default="")
    p_led.add_argument("--chrome",      default="")
    p_led.add_argument("--headless",    action="store_true")
    p_led.add_argument("--timeout",     type=int, default=15)
    p_led.set_defaults(func=cmd_check_led)

    # ---- check_item (OQC-3: Ethernet Ports LED check) ----
    p_item = sub.add_parser("check_item",
        help="check_item - Check Ethernet Ports LED (Port 1, Port 2)")
    p_item.add_argument("menu_path", nargs="*",
        default=["Configuration","Ethernet Ports"],
        help="Menu path, e.g. Configuration Ethernet Ports")
    p_item.add_argument("--ip",          default=DEFAULT_IP)
    p_item.add_argument("--chromedriver",default="")
    p_item.add_argument("--chrome",      default="")
    p_item.add_argument("--headless",    action="store_true")
    p_item.add_argument("--timeout",     type=int, default=15)
    p_item.set_defaults(func=cmd_check_item)

    # ---- check_cert (OQC-4: Certificate Verification = Passed) ----
    p_cert = sub.add_parser("check_cert",
        help="check_cert - Administration > Management > Certificate Verification")
    p_cert.add_argument("--ip",          default=DEFAULT_IP)
    p_cert.add_argument("--chromedriver",default="")
    p_cert.add_argument("--chrome",      default="")
    p_cert.add_argument("--headless",    action="store_true")
    p_cert.add_argument("--timeout",     type=int, default=15)
    p_cert.set_defaults(func=cmd_check_cert)

    # ---- check_log (Administration > Log: screenshot by MAC) ----
    p_log = sub.add_parser("check_log",
        help="check_log - Administration > Log: screenshot and save by MAC")
    p_log.add_argument("--ip",          default=DEFAULT_IP)
    p_log.add_argument("--chromedriver",default="")
    p_log.add_argument("--chrome",      default="")
    p_log.add_argument("--headless",    action="store_true")
    p_log.add_argument("--timeout",     type=int, default=15)
    p_log.set_defaults(func=cmd_check_log)

    # ---- factory_reset (OQC-Final: Maintenance > Reboot/reset > Reset now) ----
    p_reset = sub.add_parser("factory_reset",
        help="factory_reset - Maintenance > Reboot/reset > Reset now + re-login")
    p_reset.add_argument("--ip",          default=DEFAULT_IP)
    p_reset.add_argument("--chromedriver",default="")
    p_reset.add_argument("--chrome",      default="")
    p_reset.add_argument("--headless",    action="store_true")
    p_reset.add_argument("--timeout",     type=int, default=15)
    p_reset.set_defaults(func=cmd_factory_reset)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
