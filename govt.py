"""
Govt Job Finder - West Bengal
Live, non-teaching / non-defence / non-bank government jobs with direct links.

Install : pip install streamlit requests beautifulsoup4 pandas
Run     : streamlit run govt_job_finder.py

Notes
- Jobs are scraped live (cached 30 min) from public job-alert pages. If a site
  changes its layout or blocks requests, it shows as failed in "Source status";
  add other listing URLs from the sidebar.
- "Apply link" is resolved by opening each job's detail page and picking the
  best official/apply link. Always verify on the official notification.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Govt Job Finder - West Bengal", page_icon="🏛️", layout="wide")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

SOURCES = {
    "CentralStateJobs - WB": [
        "https://centralstatejobs.in/states/west-bengal",
        "https://centralstatejobs.in/states/west-bengal?page=2",
        "https://centralstatejobs.in/states/west-bengal?page=3",
    ],
    "Karmasandhan - WB": ["https://www.karmasandhan.com/jobs/state/west-bengal/"],
    "LinkingSky - WB": ["https://linkingsky.com/government-exams/government-jobs-in-west-bengal.html"],
    "FreeJobAlert": ["https://www.freejobalert.com/latest-notifications/"],
    "SarkariResult": ["https://www.sarkariresult.com/latestjob/"],
}

OFFICIAL_PORTALS = {
    "WBPSC (WBCS, Miscellaneous, Clerkship)": "https://wbpsc.gov.in",
    "WB School Service Commission (non-teaching)": "https://wbssc.gov.in",
    "WB Panchayat & Rural Development": "https://wbprd.gov.in",
    "WB Employment Bank": "https://employmentbankwb.gov.in",
    "SSC (CGL, CHSL, MTS, Steno, Selection Post)": "https://ssc.gov.in",
    "RRB Kolkata (NTPC etc.)": "https://rrbkolkata.gov.in",
    "Calcutta High Court": "https://www.calcuttahighcourt.gov.in",
    "India Post": "https://www.indiapost.gov.in",
    "Food Corporation of India": "https://fci.gov.in",
    "UPSC": "https://upsc.gov.in",
    "National Career Service": "https://www.ncs.gov.in",
}

CATEGORY_RULES = [
    ("WBPSC", r"wbpsc|west bengal public service|wbcs|clerkship|miscellaneous service"),
    ("WBSSC (non-teaching)", r"wbssc|school service commission"),
    ("WB Panchayat", r"panchayat|wbprd"),
    ("WB Municipal", r"municipal|municipality|\bkmc\b|nagarpalika|urban local"),
    ("SSC", r"\bssc\b|staff selection|\bcgl\b|\bchsl\b|\bmts\b|stenographer|selection post"),
    ("Railway", r"\brrb\b|\brrc\b|railway|ntpc|station master|goods train"),
    ("Courts", r"high court|district court|\bcourt\b|judicial|copyist|district judge"),
    ("India Post", r"india post|postal|\bgds\b|post office|dak sevak"),
    ("FCI", r"\bfci\b|food corporation"),
    ("University / Research", r"universit|institute|\biit\b|\biiser\b|\biim\b|\bnit\b|research|\bisi\b|\biiest\b|\bcsir\b|\bicar\b|college"),
]
OTHER = "Other Govt / Departments"
CENTRAL_ALL_INDIA = {"SSC", "Railway", "India Post", "FCI"}

DEFAULT_EXCLUDE = {
    "Teaching": (
        r"teacher|teaching|professor|lecturer|faculty|tutor|principal|headmaster|\btgt\b|\bpgt\b|"
        r"\bprt\b|\bslst\b|\btet\b|\bctet\b|b\.?ed\b|d\.?el\.?ed|school service commission.*teach|"
        r"assistant professor|associate professor|visiting faculty|guest (teacher|lecturer)"
    ),
    "Defence": (
        r"\barmy\b|\bnavy\b|naval|air ?force|airmen|agniveer|agnipath|defence|defense|\bbsf\b|"
        r"\bcrpf\b|\bcisf\b|\bitbp\b|\bssb\b|coast guard|military|paramilitary|armed forces|"
        r"\bnda\b|\bcds\b|afcat|assam rifles|\bcapf\b|\bnsg\b|navik|jawan|cadet|territorial army|"
        r"\bdrdo\b|ordnance|indian army|\bgd constable\b|rifleman"
    ),
    "Bank": (
        r"\bbank\b|\bbanks\b|banking|ibps|\bsbi\b|\brbi\b|nabard|sidbi|\bexim\b|gramin bank|"
        r"cooperative bank|co-operative bank|\bpnb\b|\bbob\b|\buco\b|\bidbi\b|\bhdfc\b|\bicici\b|"
        r"punjab national|canara|union bank|central bank|indian overseas|bank of"
    ),
}

# Qualification: MA English (post-graduate in a non-technical discipline)
SPECIALISED_RE = re.compile(
    r"engineer|b\.?tech|m\.?tech|\bb\.?e\b|diploma|\biti\b|mbbs|\bmd\b|nurs|pharma|\bgdmo\b|"
    r"medical officer|doctor|dentist|veterinar|technician|trade apprentice|driver|lineman|electrician|"
    r"fireman|\bmba\b|\bcost accountant|chartered accountant|\bca\b|\bicwa\b|\bllb\b|\bllm\b|"
    r"architect|agricultur|forest guard|physiotherap|laboratory|\bm\.?sc\b|\bscientist\b|physics|"
    r"chemistry|mathematics|statistic",
    re.I,
)
LOW_ONLY_RE = re.compile(r"\b10th\b|\b12th\b|matric|madhyamik|higher secondary|intermediate|8th pass|class (x|xii)\b", re.I)
DEGREE_RE = re.compile(r"graduat|post[- ]?grad|\bdegree\b|\bmaster|\bm\.?a\b|any (discipline|stream|subject)|bachelor", re.I)
BEST_FIT_RE = re.compile(
    r"english|hindi officer|translator|translation|editor|editorial|journalis|content|public relation|"
    r"information officer|publicity|librar|documentation|archiv|curator|research assistant|"
    r"executive assistant|administrative|admin\b|assistant section|section officer|office assistant|"
    r"\bclerk|lower division|\bldc\b|junior secretariat|stenograph|auditor|accountant|inspector|"
    r"wbcs|executive|\bcgl\b|\bchsl\b|copyist|typist|secretary|officer",
    re.I,
)


def qual_ok(text: str) -> bool:
    """True if an MA English (non-technical post-graduate) can apply."""
    has_degree = bool(DEGREE_RE.search(text))
    if SPECIALISED_RE.search(text) and not re.search(r"post[- ]?grad|any (discipline|stream|subject)|\bm\.?a\b", text, re.I):
        return False
    if LOW_ONLY_RE.search(text) and not has_degree:
        return False
    return True


JOB_RE = re.compile(
    r"recruitment|vacanc|notification|apply online|\bbharti\b|\bjobs?\b.*20\d\d|"
    r"walk[- ]?in|online form|\bposts?\b|\bengagement\b",
    re.I,
)
NON_JOB_RE = re.compile(
    r"^(home|about|contact|privacy|disclaimer|login|sign ?in|register|menu)\b|"
    r"admit card|answer key|\bresult\b|syllabus|previous (year )?paper|cut ?off|"
    r"hall ticket|merit list|exam date|download app|telegram|whatsapp|"
    r"view all|read more|load more|^view$|^apply$",
    re.I,
)
WB_RE = re.compile(
    r"west bengal|bengal|kolkata|calcutta|howrah|siliguri|kharagpur|santiniketan|"
    r"shibpur|barrackpore|durgapur|asansol|darjeeling|\bwb\b|wbpsc|wbssc|\bwbp\b",
    re.I,
)
SOCIAL = (
    "facebook.com", "twitter.com", "x.com", "t.me", "telegram.me", "telegram.org", "whatsapp.com",
    "youtube.com", "youtu.be", "instagram.com", "play.google.com", "linkedin.com",
    "pinterest.com", "wa.me",
)

def is_social(href: str) -> bool:
    dom = urlparse(href).netloc.lower()
    return any(dom == s or dom.endswith("." + s) for s in SOCIAL)


MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
DATE_PATTERNS = [
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.,]*{MON}[\s\-/.,]*(\d{{4}})\b", re.I), "dmy_txt"),
    (re.compile(rf"\b{MON}[\s\-/.]*(\d{{1,2}})(?:st|nd|rd|th)?,?[\s\-/.]*(\d{{4}})\b", re.I), "mdy_txt"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy_num"),
]
DEADLINE_KEYS = re.compile(r"last date|apply by|apply before|closing|deadline|till|up ?to|end date", re.I)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, timeout: int = 15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text, None
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"[:160]


def _mk_date(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def find_dates(text: str):
    """Return list of (position, date) found in text."""
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            if kind == "dmy_txt":
                dt = _mk_date(g[2], MONTHS[g[1][:3].lower()], g[0])
            elif kind == "mdy_txt":
                dt = _mk_date(g[2], MONTHS[g[0][:3].lower()], g[1])
            else:
                dt = _mk_date(g[2], g[1], g[0])
            if dt and 2020 <= dt.year <= 2035:
                out.append((m.start(), dt))
    return sorted(out)


def pick_deadline(text: str):
    found = find_dates(text)
    if not found:
        return None
    for km in DEADLINE_KEYS.finditer(text):
        after = [d for pos, d in found if km.end() <= pos <= km.end() + 40]
        if after:
            return after[0]
    return max(d for _, d in found)


def categorize(text: str) -> str:
    t = text.lower()
    for cat, rx in CATEGORY_RULES:
        if re.search(rx, t):
            return cat
    return OTHER


def row_context(a):
    """Largest ancestor text (single-job row) around an anchor."""
    ctx = a.get_text(" ", strip=True)
    node = a
    for _ in range(5):
        node = node.parent
        if node is None:
            break
        text = node.get_text(" ", strip=True)
        if len(text) > 600:
            break
        jobish = [x for x in node.find_all("a") if JOB_RE.search(x.get_text(" ", strip=True))]
        if len(jobish) > 1:
            break
        ctx = text
    return ctx


def norm_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:80]


def scrape_page(source: str, url: str):
    html, err = fetch(url)
    if err:
        return [], err
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if len(title) < 12 or len(title) > 220:
            continue
        if NON_JOB_RE.search(title) or not JOB_RE.search(title):
            continue
        href = urljoin(url, a["href"])
        if not href.startswith("http") or is_social(href):
            continue
        if href.rstrip("/") == url.rstrip("/"):
            continue
        key = norm_key(title)
        if key in seen:
            continue
        seen.add(key)
        ctx = row_context(a)
        items.append(
            {
                "title": title,
                "link": href,
                "source": source,
                "context": ctx,
                "deadline": pick_deadline(ctx),
            }
        )
    return items, None


@st.cache_data(ttl=1800, show_spinner=False)
def load_all(sources: tuple):
    """sources: tuple of (name, url). Returns (jobs list, status list)."""
    jobs, status = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda s: (s, scrape_page(s[0], s[1])), sources))
    for (name, url), (items, err) in results:
        status.append({"Source": name, "URL": url, "Jobs found": len(items), "Error": err or ""})
        jobs.extend(items)
    return jobs, status


def build_df(jobs, patterns, match_qual=True):
    rows, seen = [], set()
    for j in jobs:
        blob = f"{j['title']} {j['context']}"
        if any(re.search(p, blob, re.I) for p in patterns.values() if p):
            continue
        if match_qual and not qual_ok(blob):
            continue
        k = norm_key(j["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append(
            {
                "Job": j["title"],
                "Category": categorize(blob),
                "Last date": j["deadline"],
                "Source": j["source"],
                "Details": j["link"],
                "WB": bool(WB_RE.search(blob)) or "WB" in j["source"],
                "Fit": "⭐" if BEST_FIT_RE.search(j["title"]) else "",
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    today = date.today()
    df["Days left"] = df["Last date"].apply(lambda d: (d - today).days if d else None)
    return df


def resolve_apply(url: str):
    """Open a job detail page and return (apply_link, notification_link)."""
    html, err = fetch(url, timeout=12)
    if err:
        return "", ""
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(url).netloc.lower()
    best, best_score, notice = "", 0, ""
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        dom = urlparse(href).netloc.lower()
        if not href.startswith("http") or dom == base or is_social(href):
            continue
        txt = a.get_text(" ", strip=True)
        score = 0
        if re.search(r"apply (online|here|now|link)|online (form|application)|registration|apply$", txt, re.I):
            score += 3
        if re.search(r"\.gov\.in|\.nic\.in|\.gov\b|\.ac\.in|\.res\.in", dom):
            score += 2
        if re.search(r"official (website|site|link)|click here|login", txt, re.I):
            score += 1
        if score > best_score:
            best, best_score = href, score
        if not notice and (
            href.lower().split("?")[0].endswith(".pdf")
            or re.search(r"notification|advertisement|advt", txt, re.I)
        ):
            notice = href
    return (best if best_score >= 2 else ""), notice


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
st.title("🏛️ Govt Job Finder - West Bengal")
st.caption("Live non-teaching, non-defence, non-bank government jobs for MA English, with direct links.")

if "apply_cache" not in st.session_state:
    st.session_state.apply_cache = {}

with st.sidebar:
    st.header("Filters")
    if st.button("🔄 Refresh live data", use_container_width=True):
        load_all.clear()
        st.rerun()

    all_cats = [c for c, _ in CATEGORY_RULES] + [OTHER]
    cats = st.multiselect("Recruiter category", all_cats, default=all_cats)
    scope = st.radio(
        "Location scope",
        ["West Bengal + all-India central exams", "All India"],
        index=0,
    )
    hide_expired = st.checkbox("Hide expired", value=True)
    match_qual = st.checkbox("Match qualification: MA English", value=True)
    best_only = st.checkbox("⭐ Best-fit roles only (clerk, officer, assistant, editor, librarian...)", value=False)
    query = st.text_input("Search keyword", placeholder="clerk, assistant, SSC, court, Kolkata...")
    sort_by = st.selectbox("Sort by", ["Closing soonest", "Latest listed"])

    with st.expander("Exclusion rules (regex)"):
        patterns = {
            k: st.text_area(f"Exclude: {k}", v, height=90) for k, v in DEFAULT_EXCLUDE.items()
        }

    with st.expander("Add your own listing URLs"):
        extra = st.text_area("One URL per line", "")

sources = [(n, u) for n, urls in SOURCES.items() for u in urls]
for i, line in enumerate(x.strip() for x in extra.splitlines() if x.strip()):
    host = urlparse(line).netloc or f"Custom {i + 1}"
    sources.append((f"Custom - {host}", line))

with st.spinner("Fetching live job listings..."):
    jobs, status = load_all(tuple(sources))

df = build_df(jobs, patterns, match_qual)
tab_jobs, tab_portals, tab_status = st.tabs(["Live jobs", "Official portals", "Source status"])

with tab_jobs:
    if df.empty:
        st.warning("No jobs fetched. Check 'Source status' or add listing URLs in the sidebar.")
    else:
        f = df[df["Category"].isin(cats)].copy()
        if scope.startswith("West Bengal"):
            f = f[f["WB"] | f["Category"].isin(CENTRAL_ALL_INDIA | {"WBPSC", "WBSSC (non-teaching)", "WB Panchayat", "WB Municipal"})]
        if best_only:
            f = f[f["Fit"] == "⭐"]
        if hide_expired:
            f = f[f["Days left"].isna() | (f["Days left"] >= 0)]
        if query.strip():
            q = query.strip().lower()
            f = f[f["Job"].str.lower().str.contains(q, regex=False) | f["Category"].str.lower().str.contains(q, regex=False)]
        if sort_by == "Closing soonest":
            f = f.sort_values("Days left", na_position="last", kind="stable")

        c1, c2, c3 = st.columns(3)
        c1.metric("Live jobs shown", len(f))
        c2.metric("Closing in 7 days", int((f["Days left"].between(0, 7)).sum()))
        c3.metric("Sources working", f"{sum(1 for s in status if not s['Error'])}/{len(status)}")

        f = f.reset_index(drop=True)
        f["Apply link"] = f["Details"].map(lambda u: st.session_state.apply_cache.get(u, ("", ""))[0])
        f["Notification"] = f["Details"].map(lambda u: st.session_state.apply_cache.get(u, ("", ""))[1])

        n = st.slider("Resolve direct apply links for the first N jobs shown", 5, 80, 25, step=5)
        if st.button("🔗 Find direct apply links"):
            todo = [u for u in f["Details"].head(n) if u not in st.session_state.apply_cache]
            if todo:
                bar = st.progress(0.0, text="Opening job pages...")
                with ThreadPoolExecutor(max_workers=8) as ex:
                    for i, (u, res) in enumerate(zip(todo, ex.map(resolve_apply, todo))):
                        st.session_state.apply_cache[u] = res
                        bar.progress((i + 1) / len(todo), text=f"Resolved {i + 1}/{len(todo)}")
                bar.empty()
            st.rerun()

        show = f[["Fit", "Job", "Category", "Last date", "Days left", "Source", "Details", "Apply link", "Notification"]]
        st.dataframe(
            show,
            use_container_width=True,
            hide_index=True,
            height=620,
            column_config={
                "Fit": st.column_config.TextColumn(width="small"),
                "Job": st.column_config.TextColumn(width="large"),
                "Last date": st.column_config.DateColumn(format="DD MMM YYYY"),
                "Days left": st.column_config.NumberColumn(format="%d"),
                "Details": st.column_config.LinkColumn("Job page", display_text="Open ↗"),
                "Apply link": st.column_config.LinkColumn("Apply (official)", display_text="Apply ↗"),
                "Notification": st.column_config.LinkColumn("Notification", display_text="PDF/Notice ↗"),
            },
        )
        st.download_button(
            "⬇️ Download as CSV",
            show.to_csv(index=False).encode("utf-8"),
            "govt_jobs.csv",
            "text/csv",
        )
        st.caption("Last date is read from the listing text (best effort). Verify on the official notification before applying.")

with tab_portals:
    st.subheader("Official recruitment portals")
    for name, url in OFFICIAL_PORTALS.items():
        st.markdown(f"- **{name}** - [{url}]({url})")

with tab_status:
    st.dataframe(pd.DataFrame(status), use_container_width=True, hide_index=True)
    st.caption(f"Fetched {datetime.now():%d %b %Y, %I:%M %p}. Cached for 30 minutes.")