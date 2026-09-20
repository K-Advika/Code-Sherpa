"""Code Sherpa - Streamlit frontend.

Configuration (all optional; environment variable or .streamlit/secrets.toml):
    BACKEND_URL   Base URL of the analysis server (default: the Render deployment)
    GITHUB_TOKEN  Personal access token; raises the GitHub API limit from 60 to 5000 requests/hour
"""
import html
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
import streamlit as st

st.set_page_config(page_title="Code Sherpa", page_icon="🧭", layout="wide")


# --- 1. Configuration --------------------------------------------------------
def _setting(name, default=""):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name, default)
    except Exception:  # no secrets file present
        return default


BACKEND_BASE = str(_setting("BACKEND_URL", "http://localhost:10000")).rstrip("/")
SCAN_ENDPOINT = f"{BACKEND_BASE}/scan"
GITHUB_TOKEN = _setting("GITHUB_TOKEN")

# The original app sent the api.github.com form of the URL to /scan. Keep that behaviour;
# set to False if the backend expects the normal github.com/.../issues/N link instead.
SEND_API_URL = True

GITHUB_TIMEOUT = 10   # seconds, issue metadata lookup
WARMUP_TIMEOUT = 75   # seconds, waiting for an idle free-tier server to wake up
SCAN_TIMEOUT = 120    # seconds, the analysis itself

STAGES = (
    ("validate", "Validate link", "Parse owner, repository and issue number"),
    ("github", "Fetch issue from GitHub", "Title, state, labels and comment count"),
    ("server", "Connect to analysis server", "Wakes the free-tier instance if it is idle"),
    ("analyze", "Analyze repository", "Server downloads the repo, runs the model and saves a receipt"),
    ("verdict", "Prepare verdict", "Read the server response"),
)

PR_MESSAGE = (
    "That link is a pull request. Code Sherpa analyzes issues: open the repository's "
    "Issues tab and copy an issue link instead."
)


# --- 2. Styling --------------------------------------------------------------
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

/* ---------- Tokens ---------- */
:root {
    --bg: #0B0E13;
    --panel: #10141B;
    --panel-2: #0D1117;
    --border: #1D2430;
    --border-strong: #2E3846;
    --text: #E8ECF2;
    --text-2: #B4BDC9;
    --muted: #7C8797;
    --accent: #4DA3FF;
    --ok: #46C08A;
    --warn: #D9A441;
    --err: #E5534B;
    --ui: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    --mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

/* ---------- Base ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
    font-family: var(--ui);
    background-color: var(--bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
}
[data-testid="stAppViewContainer"] {
    background-image: radial-gradient(circle at 1px 1px, #18202B 1px, transparent 0);
    background-size: 26px 26px;
}
p, li, label, h1, h2, h3, h4, h5, h6 { font-family: var(--ui); }
::selection { background: var(--text); color: #05070A; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #262F3B; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #364253; }

/* ---------- Chrome cleanup ---------- */
[data-testid="stHeader"] { background: transparent; }
[data-testid="stDecoration"], footer, [data-testid="stAppDeployButton"] { display: none !important; }

/* ---------- Layout ---------- */
.block-container { padding: 2.5rem 2rem 4rem 2rem !important; max-width: 960px; }
[data-testid="stVerticalBlock"] { gap: 0.9rem; }

[data-testid="stSidebar"] { background-color: var(--panel); border-right: 1px solid var(--border); }
[data-testid="stSidebarUserContent"] { padding: 1.25rem 1.25rem 2rem 1.25rem !important; }
[data-testid="stSidebar"] h2 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: var(--text);
    letter-spacing: -0.01em;
    padding: 0 0 0.25rem 0 !important;
}
.side-title { font-size: 0.85rem; font-weight: 600; color: var(--text); margin: 1.6rem 0 0.4rem 0; }
.hint { font-size: 0.75rem; line-height: 1.55; color: var(--muted); margin-top: 0.6rem; }

/* ---------- Typography ---------- */
h1 {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.035em !important;
    color: var(--text);
    padding: 0 0 0.25rem 0 !important;
}
[data-testid="stMarkdownContainer"] p { font-size: 0.92rem; line-height: 1.7; color: var(--text-2); }
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 { color: var(--text); letter-spacing: -0.02em; font-weight: 600; }
[data-testid="stMarkdownContainer"] h1 { font-size: 1.4rem !important; padding: 1rem 0 0.4rem 0 !important; }
[data-testid="stMarkdownContainer"] h2 {
    font-size: 1.1rem !important;
    padding: 1rem 0 0.4rem 0 !important;
    border-bottom: 1px solid var(--border);
}
[data-testid="stMarkdownContainer"] h3 { font-size: 0.95rem !important; padding: 0.75rem 0 0.25rem 0 !important; }
[data-testid="stMarkdownContainer"] li { font-size: 0.92rem; line-height: 1.7; color: var(--text-2); }
[data-testid="stMarkdownContainer"] strong { color: var(--text); font-weight: 600; }
[data-testid="stMarkdownContainer"] a { color: var(--text); text-decoration: none; border-bottom: 1px solid var(--border-strong); }
[data-testid="stMarkdownContainer"] a:hover { border-bottom-color: #FFFFFF; }
[data-testid="stMarkdownContainer"] blockquote { border-left: 2px solid var(--border-strong); padding: 0 0 0 1rem; margin: 0.5rem 0; }
[data-testid="stMarkdownContainer"] blockquote p { color: var(--muted); }
hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 1.25rem 0 !important; }

table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th {
    font-family: var(--mono);
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    color: var(--muted) !important;
    background: var(--panel) !important;
}
th, td { border: 1px solid var(--border) !important; padding: 0.5rem 0.75rem !important; }

/* ---------- Hero ---------- */
.hero { display: flex; align-items: center; gap: 0.85rem; }
.hero svg { flex: none; }
.hero h1 { margin: 0 !important; padding: 0 !important; }
.tagline { font-size: 0.95rem; line-height: 1.6; color: var(--text-2); max-width: 62ch; margin: 0.35rem 0 1.6rem 0; }
.lede { font-size: 0.95rem; line-height: 1.7; color: var(--text-2); max-width: 66ch; margin-bottom: 0.5rem; }
.sec-title { font-size: 1rem; font-weight: 600; color: var(--text); margin: 1.4rem 0 0.7rem 0; letter-spacing: -0.01em; }

/* ---------- Form / inputs ---------- */
[data-testid="stForm"] { border: none !important; padding: 0 !important; }
[data-testid="stWidgetLabel"] p { font-size: 0.8rem !important; font-weight: 500; color: var(--text-2) !important; }
[data-testid="stTextInput"] [data-baseweb="input"] {
    background-color: #000000 !important;
    border: 1px solid #2A3340 !important;
    border-radius: 4px !important;
    box-shadow: none !important;
    transition: border-color 0.12s ease;
}
[data-testid="stTextInput"] [data-baseweb="input"]::before {
    content: "\203A";
    align-self: center;
    padding-left: 0.85rem;
    font-family: var(--mono);
    font-size: 0.95rem;
    color: #667384;
}
[data-testid="stTextInput"] [data-baseweb="input"]:hover { border-color: var(--border-strong) !important; }
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within { border-color: var(--accent) !important; box-shadow: none !important; }
[data-testid="stTextInput"] [data-baseweb="base-input"] { background-color: transparent !important; }
.stTextInput input {
    background-color: transparent !important;
    border: none !important;
    color: #FFFFFF !important;
    font-family: var(--mono) !important;
    font-size: 0.8rem !important;
    padding: 0.75rem 0.75rem 0.75rem 0.5rem !important;
    caret-color: #FFFFFF;
    box-shadow: none !important;
}
.stTextInput input::placeholder { color: #566171 !important; opacity: 1; }
[data-testid="InputInstructions"] { display: none; }

/* ---------- Buttons ---------- */
.stButton > button, [data-testid="stFormSubmitButton"] > button {
    background-color: var(--text) !important;
    color: #05070A !important;
    border: 1px solid var(--text) !important;
    border-radius: 4px !important;
    font-family: var(--ui) !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    padding: 0.65rem 1rem !important;
    min-height: 0;
    width: 100%;
    box-shadow: none !important;
    transition: background-color 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.stButton > button p, [data-testid="stFormSubmitButton"] > button p,
.stDownloadButton > button p, [data-testid="stDownloadButton"] > button p {
    color: inherit !important; font-family: inherit !important; font-size: inherit !important; margin: 0;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    background-color: var(--bg) !important; color: #FFFFFF !important; border-color: #FFFFFF !important;
}
.stButton > button:focus-visible, [data-testid="stFormSubmitButton"] > button:focus-visible,
.stDownloadButton > button:focus-visible, [data-testid="stDownloadButton"] > button:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
}
.stDownloadButton > button, [data-testid="stDownloadButton"] > button {
    background-color: transparent !important;
    color: var(--text) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 4px !important;
    font-family: var(--ui) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 0.5rem 0.9rem !important;
    min-height: 0;
    box-shadow: none !important;
    transition: border-color 0.12s ease, background-color 0.12s ease;
}
.stDownloadButton > button:hover, [data-testid="stDownloadButton"] > button:hover {
    background-color: var(--panel) !important; border-color: var(--text) !important; color: #FFFFFF !important;
}

/* ---------- Code ---------- */
code {
    font-family: var(--mono) !important;
    font-size: 0.85em;
    background-color: #141A22 !important;
    border: 1px solid #263040 !important;
    border-radius: 4px !important;
    padding: 0.1em 0.4em;
    color: var(--text);
}
pre, [data-testid="stCode"] pre {
    background-color: var(--panel-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
    font-family: var(--mono) !important;
    font-size: 0.8rem;
    line-height: 1.6;
}
pre code, [data-testid="stCode"] code { background: transparent !important; border: none !important; padding: 0 !important; font-size: inherit; }

/* ---------- Expanders ---------- */
[data-testid="stExpander"] { border: none !important; background: transparent !important; }
[data-testid="stExpander"] details {
    background-color: var(--panel-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}
[data-testid="stExpander"] summary { padding: 0.7rem 0.9rem !important; color: #A9B3C0; transition: color 0.12s ease, background-color 0.12s ease; }
[data-testid="stExpander"] summary:hover { color: #FFFFFF; background-color: var(--panel); }
[data-testid="stExpander"] summary p { font-size: 0.85rem !important; color: inherit !important; margin: 0; font-weight: 500; }
[data-testid="stExpanderDetails"] { border-top: 1px solid var(--border); padding: 0.9rem !important; }

/* ---------- Bordered container (verdict panel) ---------- */
[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--border) !important; border-radius: 6px !important; }

/* ---------- Alerts ---------- */
[data-testid="stAlert"] > div {
    background-color: var(--panel-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text-2) !important;
}
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) > div { border-color: #5A2626 !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) > div { border-color: #55431A !important; }
[data-testid="stAlert"] p { font-size: 0.85rem !important; color: var(--text-2) !important; }

/* ---------- Route tracker (live pipeline) ---------- */
.route { border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); padding: 0.35rem 1.15rem; }
.wp { position: relative; display: flex; align-items: flex-start; gap: 0.85rem; padding: 0.7rem 0; }
.wp:not(:last-child)::before {
    content: ""; position: absolute; left: 5px; top: 1.6rem; bottom: -0.6rem; width: 1px; background: var(--border-strong);
}
.wp.done:not(:last-child)::before { background: var(--ok); opacity: 0.55; }
.wp-dot {
    flex: none; width: 11px; height: 11px; margin-top: 0.32rem; border-radius: 50%;
    border: 1.5px solid var(--border-strong); background: var(--panel-2); position: relative; z-index: 1;
}
.wp.active .wp-dot { border-color: var(--accent); background: var(--accent); animation: pulse 1.6s ease-out infinite; }
.wp.done .wp-dot { border-color: var(--ok); background: var(--ok); }
.wp.warn .wp-dot { border-color: var(--warn); background: var(--warn); }
.wp.error .wp-dot { border-color: var(--err); background: var(--err); }
.wp-body { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.wp-name { font-size: 0.9rem; font-weight: 500; color: var(--text); }
.wp.pending .wp-name, .wp.skipped .wp-name { color: var(--muted); }
.wp-detail { font-family: var(--mono); font-size: 0.74rem; line-height: 1.5; color: var(--muted); overflow-wrap: anywhere; }
.wp.warn .wp-detail { color: var(--warn); }
.wp.error .wp-detail { color: var(--err); }
.wp-time { font-family: var(--mono); font-size: 0.74rem; color: var(--muted); padding-top: 0.2rem; white-space: nowrap; }
@keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(77, 163, 255, 0.55); }
    100% { box-shadow: 0 0 0 9px rgba(77, 163, 255, 0); }
}
@media (prefers-reduced-motion: reduce) { .wp.active .wp-dot { animation: none; } }

/* ---------- Issue brief ---------- */
.brief { border: 1px solid var(--border); border-radius: 6px; background: var(--panel); padding: 1rem 1.15rem; margin-bottom: 1rem; }
.brief-top { display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem; font-family: var(--mono); font-size: 0.78rem; color: var(--muted); }
.pill { font-size: 0.72rem; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-strong); color: var(--text-2); }
.pill.open { color: var(--ok); border-color: rgba(70, 192, 138, 0.4); }
.brief-title { font-size: 1.05rem; font-weight: 600; line-height: 1.4; color: var(--text); margin: 0.6rem 0 0.45rem 0; }
.brief-meta { display: flex; flex-wrap: wrap; gap: 0.3rem 1.2rem; font-size: 0.8rem; color: var(--muted); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 0.75rem; }
.chip { font-family: var(--mono); font-size: 0.72rem; color: var(--text-2); border: 1px solid var(--border-strong); border-radius: 4px; padding: 2px 8px; }

/* ---------- Verdict ---------- */
.verdict-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.4rem; margin: 1.4rem 0 0.3rem 0; }
.verdict-head .t { font-size: 1.05rem; font-weight: 600; color: var(--text); letter-spacing: -0.01em; }
.verdict-head .m { font-family: var(--mono); font-size: 0.74rem; color: var(--muted); }
.receipt { font-size: 0.78rem; color: var(--muted); }


/* ---------- Guide: finding an issue URL ---------- */
.g-steps { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--border); border-radius: 6px; background: var(--panel); }
.g-step { padding: 1rem 1.1rem; border-right: 1px solid var(--border); }
.g-step:last-child { border-right: none; }
.g-n {
    display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; margin-bottom: 0.65rem;
    border: 1px solid var(--border-strong); border-radius: 50%; font-family: var(--mono); font-size: 0.72rem; color: var(--text);
}
.g-t { display: block; font-size: 0.92rem; font-weight: 600; color: var(--text); margin-bottom: 0.3rem; }
.g-d { display: block; font-size: 0.82rem; line-height: 1.6; color: var(--text-2); }
.anatomy { margin-top: 0.9rem; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); padding: 1rem 1.15rem; }
.a-title { font-size: 0.9rem; font-weight: 600; color: var(--text); margin-bottom: 0.2rem; }
.a-sub { font-size: 0.8rem; color: var(--muted); margin-bottom: 0.7rem; }
.a-url {
    font-family: var(--mono); font-size: 0.82rem; color: var(--text-2); white-space: nowrap; overflow-x: auto;
    padding: 0.65rem 0.85rem; background: #000000; border: 1px solid var(--border); border-radius: 4px; margin-bottom: 0.5rem;
}
.a-url.example { background: transparent; }
.seg { border-radius: 3px; padding: 0.05em 0.3em; }
.seg.owner { color: #7CC4FF; background: rgba(77, 163, 255, 0.13); }
.seg.repo { color: #6FD3A8; background: rgba(70, 192, 138, 0.13); }
.seg.num { color: #E8C170; background: rgba(217, 164, 65, 0.13); }
.a-legend { display: flex; flex-wrap: wrap; gap: 0.4rem 1.6rem; margin-top: 0.8rem; font-size: 0.8rem; color: var(--text-2); }
.a-next { margin-top: 0.9rem; font-size: 0.85rem; color: var(--text-2); }
@media (max-width: 720px) {
    .g-steps { grid-template-columns: 1fr; }
    .g-step { border-right: none; border-bottom: 1px solid var(--border); }
    .g-step:last-child { border-bottom: none; }
}
</style>
"""

LOGO = (
    "<svg width='34' height='34' viewBox='0 0 34 34' fill='none' stroke='#E8ECF2' stroke-width='1.6' "
    "stroke-linecap='round' stroke-linejoin='round'>"
    "<path d='M3 28 L13 12 L18 20 L22 14 L31 28 Z'/><path d='M13 12 V5'/><path d='M13 5 L19 7.2 L13 9.4'/></svg>"
)

st.markdown(CSS, unsafe_allow_html=True)


# --- 3. GitHub URL handling --------------------------------------------------
@dataclass
class IssueRef:
    owner: str
    repo: str
    number: int

    @property
    def slug(self):
        return f"{self.owner}/{self.repo}"

    @property
    def html_url(self):
        return f"https://github.com/{self.owner}/{self.repo}/issues/{self.number}"

    @property
    def api_url(self):
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{self.number}"


_ISSUE_PATTERNS = (
    re.compile(
        r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?P<kind>issues|pull)/(?P<num>\d+)(?:[/?#].*)?$",
        re.I,
    ),
    re.compile(
        r"^https?://api\.github\.com/repos/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?P<kind>issues|pulls)/(?P<num>\d+)/?$",
        re.I,
    ),
)


def parse_issue_url(raw):
    """Return (IssueRef, None) for a valid issue link, otherwise (None, error message).

    Accepts github.com issue links (with or without https://) and api.github.com/repos links.
    """
    text = (raw or "").strip()
    if not text:
        return None, "Paste a GitHub issue URL to begin."
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    for pattern in _ISSUE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        if match.group("kind").lower() in ("pull", "pulls"):
            return None, PR_MESSAGE
        owner, repo = match.group("owner"), match.group("repo")
        if set(owner) <= {"."} or set(repo) <= {"."}:
            break
        return IssueRef(owner, repo, int(match.group("num"))), None
    return None, (
        "This doesn't look like a GitHub issue URL. It should look like "
        "`https://github.com/<owner>/<repository-name>/issues/<issue-number>`. "
        "The guide below shows where to find it."
    )


def fetch_issue_meta(ref):
    """Look up issue metadata on GitHub. Returns (outcome, meta, note).

    outcome: "ok" | "not_found" | "pull_request" | "skipped" (rate limit / network problem; not fatal)
    """
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "code-sherpa-frontend"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        resp = requests.get(ref.api_url, headers=headers, timeout=GITHUB_TIMEOUT)
    except requests.RequestException:
        return "skipped", None, "GitHub unreachable from this app; continuing without preview"
    if resp.status_code == 200:
        try:
            meta = resp.json()
        except ValueError:
            return "skipped", None, "Unreadable GitHub response; continuing without preview"
        if isinstance(meta, dict) and "pull_request" in meta:
            return "pull_request", meta, "This is a pull request"
        return "ok", meta, ""
    if resp.status_code == 404:
        return "not_found", None, "Issue not found"
    if resp.status_code in (403, 429):
        return "skipped", None, "GitHub rate limit reached; continuing without preview"
    return "skipped", None, f"GitHub returned HTTP {resp.status_code}; continuing without preview"


# --- 4. Backend calls (run off the main thread so the UI can show a live timer) ---
def run_in_background(fn, *args, **kwargs):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    executor.shutdown(wait=False)  # the worker exits by itself once the request finishes
    return future


def wait_for(future, on_tick, interval=0.4):
    while not future.done():
        on_tick()
        time.sleep(interval)
    return future.result()  # re-raises any request exception here


def wake_server(on_tick):
    """Poll the server root until it answers. A free-tier instance can take ~30-60s to wake."""
    began = time.perf_counter()
    while True:
        remaining = WARMUP_TIMEOUT - (time.perf_counter() - began)
        if remaining <= 0:
            raise requests.exceptions.Timeout("server did not respond in time")
        future = run_in_background(requests.get, BACKEND_BASE + "/", timeout=remaining)
        resp = wait_for(future, lambda: on_tick(time.perf_counter() - began))
        if resp.status_code not in (502, 503, 504):  # any other status means the app is up
            return resp
        time.sleep(2)  # the platform proxy is still starting the instance


@st.cache_data(ttl=60, show_spinner=False)
def ping_backend():
    """Cheap status probe for the sidebar. Also nudges an idle server to start waking."""
    began = time.perf_counter()
    try:
        resp = requests.get(BACKEND_BASE + "/", timeout=4)
        return {"state": "online", "ms": int((time.perf_counter() - began) * 1000), "code": resp.status_code}
    except requests.exceptions.Timeout:
        return {"state": "idle"}
    except requests.RequestException:
        return {"state": "offline"}


def backend_error_detail(resp):
    try:
        body = resp.json()
        if isinstance(body, dict):
            return str(body.get("detail") or body.get("error") or body)[:400]
    except ValueError:
        pass
    return (resp.text or resp.reason or "No details returned")[:400]


# --- 5. Live pipeline tracker ------------------------------------------------
def pipeline_html(stages):
    rows = []
    for stage in stages:
        secs = f"{stage['secs']:.1f}s" if stage["secs"] is not None else ""
        detail = html.escape(stage["detail"] or stage["hint"])
        rows.append(
            f"<div class='wp {stage['state']}'><span class='wp-dot'></span>"
            f"<div class='wp-body'><span class='wp-name'>{html.escape(stage['name'])}</span>"
            f"<span class='wp-detail'>{detail}</span></div>"
            f"<span class='wp-time'>{secs}</span></div>"
        )
    return "<div class='route'>" + "".join(rows) + "</div>"


class Pipeline:
    """Holds stage state and re-renders the tracker into a placeholder on every change."""

    def __init__(self, slot):
        self.slot = slot
        self.stages = [
            {"key": k, "name": n, "hint": h, "state": "pending", "detail": "", "secs": None} for k, n, h in STAGES
        ]
        self._began = {}
        self._render()

    def _get(self, key):
        return next(s for s in self.stages if s["key"] == key)

    def _render(self):
        self.slot.markdown(pipeline_html(self.stages), unsafe_allow_html=True)

    def start(self, key, detail=""):
        self._get(key).update(state="active", detail=detail, secs=None)
        self._began[key] = time.perf_counter()
        self._render()

    def tick(self, key, detail, secs):
        self._get(key).update(detail=detail, secs=secs)
        self._render()

    def elapsed(self, key):
        return time.perf_counter() - self._began[key]

    def done(self, key, detail, state="done"):
        self._get(key).update(state=state, detail=detail, secs=self.elapsed(key))
        self._render()

    def fail(self, key, detail):
        self.done(key, detail, state="error")
        for stage in self.stages:  # everything after a failure is not going to run
            if stage["state"] == "pending":
                stage.update(state="skipped", detail="Not run")
        self._render()


# --- 6. Rendering helpers ----------------------------------------------------
def brief_html(ref, meta):
    e = html.escape
    state = (meta or {}).get("state", "")
    top = (
        f"<div class='brief-top'><a href='{e(ref.html_url)}' target='_blank' rel='noopener'>{e(ref.slug)}</a>"
        f"<span>#{ref.number}</span>"
    )
    if state:
        top += f"<span class='pill {e(state)}'>{e(state)}</span>"
    top += "</div>"
    if not meta:
        return f"<div class='brief'>{top}</div>"

    author = (meta.get("user") or {}).get("login", "unknown")
    opened = str(meta.get("created_at", ""))[:10]
    comments = meta.get("comments", 0)
    labels = [l.get("name", "") for l in meta.get("labels", []) if isinstance(l, dict) and l.get("name")]
    body = f"<div class='brief-title'>{e(str(meta.get('title', '')))}</div>"
    body += (
        f"<div class='brief-meta'><span>Opened by {e(author)}</span><span>{e(opened)}</span>"
        f"<span>{comments} comment{'s' if comments != 1 else ''}</span></div>"
    )
    if labels:
        body += "<div class='chips'>" + "".join(f"<span class='chip'>{e(name)}</span>" for name in labels[:8]) + "</div>"
    return f"<div class='brief'>{top}{body}</div>"





def guide_html():
    return (
        "<div class='g-steps'>"
        "<div class='g-step'><span class='g-n'>1</span><span class='g-t'>Open the Issues tab</span>"
        "<span class='g-d'>Open the repository in your browser and click the <strong>Issues</strong> tab in the top "
        "navigation bar, right next to <strong>Code</strong>.</span></div>"
        "<div class='g-step'><span class='g-n'>2</span><span class='g-t'>Find the issue number</span>"
        "<span class='g-d'>In the list of open issues, look beside or beneath each title for a hashtag followed by "
        "digits, like <code>#1</code> or <code>#42</code>. That is the issue number.</span></div>"
        "<div class='g-step'><span class='g-n'>3</span><span class='g-t'>Copy the issue URL</span>"
        "<span class='g-d'>Click the issue title to open it, then copy the full address from your browser's "
        "address bar. That is the issue URL.</span></div>"
        "</div>"
        "<div class='anatomy'><div class='a-title'>Anatomy of an issue URL</div>"
        "<div class='a-sub'>The URL always follows this structure:</div>"
        "<div class='a-url'>https://github.com/<span class='seg owner'>&lt;owner&gt;</span>/"
        "<span class='seg repo'>&lt;repository-name&gt;</span>/issues/<span class='seg num'>&lt;issue-number&gt;</span></div>"
        "<div class='a-url example'>https://github.com/<span class='seg owner'>psf</span>/"
        "<span class='seg repo'>requests</span>/issues/<span class='seg num'>6000</span></div>"
        "<div class='a-legend'>"
        "<span><span class='seg owner'>owner</span> the account or organization that owns the repository</span>"
        "<span><span class='seg repo'>repository-name</span> the project's name</span>"
        "<span><span class='seg num'>issue-number</span> the number after the hashtag</span></div>"
        "<div class='a-next'>Paste the URL into the sidebar and click <strong>Analyze issue</strong>.</div></div>"
    )


def render_guide_section():
    st.markdown("<div class='sec-title'>How to find an issue URL</div>", unsafe_allow_html=True)
    st.markdown(guide_html(), unsafe_allow_html=True)


def render_empty_state():
    st.markdown(
        "<div class='lede'>Paste a GitHub issue link in the sidebar. Code Sherpa reads the issue and its repository, "
        "then explains what is going on and where to start.</div>",
        unsafe_allow_html=True,
    )
    render_guide_section()


def show_result(res):
    ref = res["ref"]
    st.markdown(brief_html(ref, res["meta"]), unsafe_allow_html=True)
    st.markdown(
        f"<div class='verdict-head'><span class='t'>Verdict</span>"
        f"<span class='m'>completed in {res['elapsed']:.1f}s</span></div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(res["verdict"])
    if res["receipt"]:
        st.markdown(
            f"<div class='receipt'>Receipt: <code>{html.escape(str(res['receipt']))}</code></div>",
            unsafe_allow_html=True,
        )
    st.download_button(
        "Download verdict (.md)",
        data=res["verdict"],
        file_name=f"code-sherpa_{ref.owner}_{ref.repo}_{ref.number}.md",
        mime="text/markdown",
    )
    with st.expander("Run log"):
        st.markdown(pipeline_html(res["stages"]), unsafe_allow_html=True)
    with st.expander("How to find an issue URL"):
        st.markdown(guide_html(), unsafe_allow_html=True)


# --- 7. The analysis run -----------------------------------------------------
def run_analysis(raw_url):
    st.session_state["result"] = None
    started = time.perf_counter()
    brief_slot = st.empty()
    pipe = Pipeline(st.empty())

    # 1. Validate the link locally
    pipe.start("validate", "Parsing link")
    ref, error = parse_issue_url(raw_url)
    if error:
        pipe.fail("validate", "Link not recognized")
        st.error(error)
        render_guide_section()
        return
    pipe.done("validate", f"{ref.slug}, issue #{ref.number}")

    # 2. Real GitHub lookup: confirms the issue exists and gives us something to show while we wait
    pipe.start("github", "Requesting issue metadata")
    outcome, meta, note = fetch_issue_meta(ref)
    if outcome == "pull_request":
        pipe.fail("github", note)
        st.error(PR_MESSAGE)
        return
    if outcome == "not_found":
        pipe.fail("github", note)
        st.error(
            f"GitHub has no issue #{ref.number} in {ref.slug}. Check the number, and make sure the repository is public."
        )
        return
    if outcome == "ok":
        pipe.done("github", f"{meta.get('state', 'unknown')}, {meta.get('comments', 0)} comments")
        brief_slot.markdown(brief_html(ref, meta), unsafe_allow_html=True)
    else:
        pipe.done("github", note, state="warn")
        meta = None

    # 3. Wake the free-tier server (live timer)
    pipe.start("server", "Contacting server")

    def server_tick(secs):
        label = "Contacting server" if secs < 4 else "Waking server from idle (free-tier cold start)"
        pipe.tick("server", label, secs)

    try:
        wake_server(server_tick)
    except requests.RequestException as exc:
        pipe.fail("server", "No response from server")
        st.error(
            f"Could not reach the analysis server at {urlparse(BACKEND_BASE).netloc} ({type(exc).__name__}). "
            "Try again in a minute. If it keeps failing, check that the backend is deployed."
        )
        return
    warm_secs = pipe.elapsed("server")
    pipe.done("server", "Online after cold start" if warm_secs > 6 else "Online")

    # 4. The analysis itself (single blocking request on the server, so we show honest elapsed time)
    pipe.start("analyze", "Request sent")
    payload_url = ref.api_url if SEND_API_URL else ref.html_url
    future = run_in_background(requests.post, SCAN_ENDPOINT, json={"github_url": payload_url}, timeout=SCAN_TIMEOUT)

    def analyze_tick():
        secs = pipe.elapsed("analyze")
        pipe.tick("analyze", f"Waiting on server, up to {SCAN_TIMEOUT}s allowed", secs)

    try:
        resp = wait_for(future, analyze_tick)
    except requests.exceptions.ReadTimeout:
        pipe.fail("analyze", f"No answer within {SCAN_TIMEOUT}s")
        st.error("The server took too long to finish this analysis. Large repositories can exceed the limit. Try again or pick a smaller repository.")
        return
    except requests.RequestException as exc:
        pipe.fail("analyze", type(exc).__name__)
        st.error(f"Connection to the server failed: {exc}")
        return

    if resp.status_code >= 400:
        pipe.fail("analyze", f"Server returned HTTP {resp.status_code}")
        st.error(f"The server rejected the request (HTTP {resp.status_code}). Its message:")
        st.code(backend_error_detail(resp), language="text")
        return
    pipe.done("analyze", f"HTTP {resp.status_code}, {len(resp.content) / 1024:.1f} KB received")

    # 5. Read the response
    pipe.start("verdict", "Reading response")
    try:
        data = resp.json()
    except ValueError:
        data = None
    verdict = data.get("verdict") if isinstance(data, dict) else None
    if not verdict:
        pipe.fail("verdict", "Response had no verdict field")
        st.error("The server answered, but the response did not include a verdict.")
        if isinstance(data, dict):
            st.code(", ".join(data.keys()) or "(empty object)", language="text")
        return
    receipt = next(
        (data[k] for k in ("receipt_url", "receipt", "s3_url", "s3_key", "receipt_key") if data.get(k)), None
    )
    pipe.done("verdict", "Receipt reported by server" if receipt else "Verdict ready")

    st.session_state["result"] = {
        "ref": ref,
        "meta": meta,
        "verdict": verdict,
        "receipt": receipt,
        "elapsed": time.perf_counter() - started,
        "stages": [dict(s) for s in pipe.stages],
    }
    brief_slot.empty()
    pipe.slot.empty()
    show_result(st.session_state["result"])


# --- 8. Page -----------------------------------------------------------------
st.session_state.setdefault("result", None)

st.markdown(
    f"<div class='hero'>{LOGO}<h1>Code Sherpa</h1></div>"
    "<div class='tagline'>An issue triage tool that walks you through unfamiliar repositories.</div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Workspace setup")
    with st.form("scan_form"):
        issue_url = st.text_input("GitHub issue URL", placeholder="https://github.com/owner/repo/issues/123")
        submitted = st.form_submit_button("Analyze issue", type="primary")
    st.markdown(
        "<div class='hint'>Press Enter or click Analyze. Both github.com and api.github.com links work. "
        "Pull requests are not supported.</div>",
        unsafe_allow_html=True,
    )
    
if submitted:
    if not issue_url.strip():
        st.warning("Paste a GitHub issue URL in the sidebar, then click Analyze issue.")
        render_empty_state()
    else:
        run_analysis(issue_url)
elif st.session_state["result"]:
    show_result(st.session_state["result"])
else:
    render_empty_state()
