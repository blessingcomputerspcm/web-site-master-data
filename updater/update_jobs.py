"""
Web Site Master - Daily Job Auto Updater
Blessing Computers, Pavoorchatram

Runs every day on GitHub Actions:
 1. Reads official govt recruitment pages listed in sources.json
 2. Finds new notification links (and optionally asks Gemini + Google Search)
 3. Uses AI (Gemini by default) to extract job details in Tamil + English
 4. Validates (official domain, future last date, no duplicates)
 5. Writes data/jobs.json, which the Web Site Master software reads
"""
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
SOURCES_PATH = os.path.join(ROOT, "sources.json")
JOBS_PATH = os.path.join(ROOT, "data", "jobs.json")
SEEN_PATH = os.path.join(ROOT, "data", "seen.json")

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()
START = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

INCLUDE_WORDS = ["recruit", "notification", "advt", "advertisement", "vacanc", "cen ", "cen-",
                 "apply", "engagement", "notice for", "gds", "constable", "assistant", "officer",
                 "posts", "post of", "selection", "agniveer", "apprentice", "clerk", "exam"]
EXCLUDE_WORDS = ["result", "answer key", "admit card", "hall ticket", "call letter", "syllabus",
                 "tender", "cut off", "cut-off", "cutoff", "marks", "rank list", "interview schedule",
                 "provisional", "selected candidates", "score card", "scorecard", "certificate verification",
                 "objection", "rti", "annual report", "press release", "corrigendum to tender"]


def log(*a):
    print(datetime.now(IST).strftime("%H:%M:%S"), *a, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ fetching
def http_get(url, timeout=30):
    """GET with fallback for govt sites that have broken SSL certificates."""
    headers = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9,ta;q=0.8"}
    try:
        return requests.get(url, headers=headers, timeout=(12, timeout))
    except requests.exceptions.SSLError:
        return requests.get(url, headers=headers, timeout=(12, timeout), verify=False)


def page_links(url):
    r = http_get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = urljoin(r.url, a["href"].strip())
        if href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        out.append((text, href))
    return out


def looks_like_job(text, href):
    s = (text + " " + href).lower()
    if any(w in s for w in EXCLUDE_WORDS):
        return False
    return any(w in s for w in INCLUDE_WORDS) and len(text) >= 8


def doc_text(url, max_chars):
    """Return readable text of a web page or PDF."""
    r = http_get(url, timeout=60)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        from pdfminer.high_level import extract_text
        text = extract_text(io.BytesIO(r.content), maxpages=6)
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header"]):
            t.decompose()
        text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return text[:max_chars]


# ------------------------------------------------------------------ AI providers
class AIError(Exception):
    pass


class Gemini:
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, key, model):
        self.key = key
        if model and model != "auto":
            self.models = [model]
        else:
            self.models = self.list_models()
        self.idx = 0
        self.search_ok = True
        self.search_fail = 0
        log("Gemini models to try:", ", ".join(self.models[:6]))

    @property
    def model(self):
        return self.models[self.idx]

    def list_models(self):
        """Flash models that support generateContent: stable first, newest first."""
        out = []
        try:
            r = requests.get(f"{self.BASE}/models", params={"pageSize": 200},
                             headers={"x-goog-api-key": self.key}, timeout=30)
            r.raise_for_status()
            cands = []
            for m in r.json().get("models", []):
                name = m["name"].split("/")[-1]
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                low = name.lower()
                if "flash" not in low or any(x in low for x in ["image", "tts", "live", "audio", "thinking", "exp"]):
                    continue
                ver = re.findall(r"(\d+(?:\.\d+)?)", low)
                stable = "preview" not in low and "latest" not in low
                lite = "lite" in low
                cands.append((stable, not lite, float(ver[0]) if ver else 0, name))
            cands.sort(reverse=True)
            out = [c[3] for c in cands]
        except Exception as e:
            log("Model list failed:", e)
        for extra in ["gemini-flash-latest", "gemini-flash-lite-latest"]:
            if extra not in out:
                out.append(extra)
        return out

    def next_model(self, why):
        if self.idx + 1 < len(self.models):
            self.idx += 1
            log(f"  switching Gemini model -> {self.model} ({why})")
            return True
        return False

    def ask(self, prompt, use_search=False):
        if use_search and not self.search_ok:
            raise AIError("Google Search mode off for this run")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1}}
        if use_search:
            body["tools"] = [{"google_search": {}}]
        else:
            body["generationConfig"]["responseMimeType"] = "application/json"
        waits = 0
        while True:
            r = requests.post(f"{self.BASE}/models/{self.model}:generateContent",
                              headers={"x-goog-api-key": self.key}, json=body, timeout=120)
            if r.status_code == 200:
                break
            msg = r.text[:600]
            if r.status_code == 429:
                low = msg.lower()
                log("  Gemini 429:", " ".join(msg.split())[:220])
                m = re.search(r'"retryDelay":\s*"(\d+)', msg)
                delay = int(m.group(1)) + 2 if m else 30
                if "limit: 0" in low or "perday" in low or "per day" in low or delay > 90:
                    # this model has no (or no more) free quota today -> try another model
                    if use_search:
                        self.search_fail += 1
                        if self.search_fail >= 2:
                            self.search_ok = False
                            log("  Google Search mode has no free quota - turned off for this run")
                        raise AIError("search quota")
                    if self.next_model("no free quota"):
                        continue
                    raise AIError("Gemini daily free quota finished: " + msg[:200])
                if waits >= 2:
                    raise AIError("Gemini busy: " + msg[:200])
                waits += 1
                log(f"  Gemini per-minute limit, waiting {delay}s")
                time.sleep(min(delay, 70))
                continue
            if r.status_code >= 500 and waits < 2:
                waits += 1
                time.sleep(15)
                continue
            if r.status_code in (400, 404) and use_search:
                self.search_ok = False
                raise AIError("Google Search not supported: " + msg[:200])
            if r.status_code == 404 and self.next_model("model not found"):
                continue
            raise AIError(f"Gemini {r.status_code}: {msg[:300]}")
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except Exception:
            raise AIError("Gemini empty answer")


class OpenAIChat:
    def __init__(self, key, model):
        self.key, self.model = key, model or "gpt-4o-mini"

    def ask(self, prompt, use_search=False):
        if use_search:
            raise AIError("search mode not supported for this provider")
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers={"Authorization": f"Bearer {self.key}"},
                          json={"model": self.model, "temperature": 0.1,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        if r.status_code != 200:
            raise AIError(f"OpenAI {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


class ClaudeChat:
    def __init__(self, key, model):
        self.key, self.model = key, model or "claude-haiku-4-5"

    def ask(self, prompt, use_search=False):
        if use_search:
            raise AIError("search mode not supported for this provider")
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                          json={"model": self.model, "max_tokens": 4000,
                                "messages": [{"role": "user", "content": prompt + "\nReply with JSON only."}]},
                          timeout=120)
        if r.status_code != 200:
            raise AIError(f"Claude {r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json().get("content", []))


def build_providers(cfg):
    """Provider order: chosen one first, then the others that have a key (backup)."""
    env = {"gemini": "GEMINI_API_KEY", "chatgpt": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}
    cls = {"gemini": Gemini, "chatgpt": OpenAIChat, "claude": ClaudeChat}
    order = [cfg.get("ai_provider", "gemini")] + [p for p in cfg.get("backup_order", []) if p != cfg.get("ai_provider")]
    out = []
    for p in order:
        key = os.environ.get(env.get(p, ""), "").strip()
        if p in cls and key:
            try:
                out.append((p, cls[p](key, cfg.get("models", {}).get(p))))
            except Exception as e:
                log("Provider init failed", p, e)
    return out


class AI:
    def __init__(self, cfg):
        self.providers = build_providers(cfg)
        self.delay = cfg.get("seconds_between_ai_calls", 7)
        self.calls = 0
        self.max_calls = cfg.get("max_ai_calls_per_run", 60)
        if not self.providers:
            log("ERROR: no AI API key found. Add GEMINI_API_KEY in GitHub Secrets.")

    def ask_json(self, prompt, use_search=False):
        if time.time() - START > 28 * 60:
            raise AIError("time limit for this run reached")
        if self.calls >= self.max_calls:
            raise AIError("max AI calls for this run reached")
        last = None
        for name, p in self.providers:
            if use_search and name != "gemini":
                continue
            try:
                time.sleep(self.delay)
                self.calls += 1
                return parse_json(p.ask(prompt, use_search))
            except Exception as e:
                last = e
                log(f"  {name} failed: {e}")
        raise AIError(f"all providers failed: {last}")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            return json.loads(m.group(1))
        raise AIError("AI did not return JSON")


# ------------------------------------------------------------------ prompts
FIELDS = """Each job object must have these keys:
"is_recruitment": true only if this is a NEW job recruitment notification that people can apply for (false for results, admit cards, answer keys, tenders, syllabus, corrigenda),
"org": organisation short name (e.g. "TNPSC", "RRB", "SSC"),
"post": post / exam name in English (short, max 120 chars),
"postTa": same in Tamil,
"total": total vacancies as text (e.g. "6574" or "Various"),
"start": application start date YYYY-MM-DD or "",
"last": last date to apply YYYY-MM-DD (required, "" if not found),
"qual": educational qualification in short English,
"age": age limit in short English,
"fee": application fee in short English,
"docs": list of documents needed to apply, each written as "English / Tamil" (e.g. "Passport size photo / புகைப்படம்"),
"notifyUrl": official notification link (PDF or page),
"applyUrl": official apply online link,
"note": one short line about exam date or anything important (English)."""


def extract_prompt(src, link_text, link_url, text):
    return f"""You are helping an Indian e-Sevai (online service) centre. Today is {TODAY.isoformat()}.
Below is text from an official page of {src['name']}.
Link title: {link_text}
Link URL: {link_url}

Read it and return a JSON object: {{"jobs": [ ... ]}} (empty list if not a recruitment notification).
{FIELDS}
Use only facts in the text. Do not guess dates. If the apply link is not in the text, use "{src.get('apply', src['url'])}".

TEXT:
{text}"""


def search_prompt(src):
    return f"""Today is {TODAY.isoformat()}. Use Google Search to find recruitment notifications from {src['name']} ({src['url']})
for which online application is OPEN NOW (last date on or after today). Only official notifications.
Return JSON only: {{"jobs": [ ... ]}}
{FIELDS}
notifyUrl and applyUrl must be official {src['name']} / Government of India / State Government links, not job news sites.
If nothing is open, return {{"jobs": []}}."""


# ------------------------------------------------------------------ validation
def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def job_key(j):
    return norm(j.get("org"))[:20] + "|" + norm(j.get("post"))[:50]


def domain_ok(url, allowed):
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def clean_job(j, src, allowed, how):
    if not isinstance(j, dict) or not j.get("is_recruitment", True):
        return None
    last = parse_date(j.get("last"))
    if not last or last < TODAY or last > TODAY + timedelta(days=150):
        return None
    if not j.get("post"):
        return None
    apply_url = j.get("applyUrl") or ""
    notify_url = j.get("notifyUrl") or ""
    if how == "search" and not (domain_ok(apply_url, allowed) or domain_ok(notify_url, allowed)):
        return None  # search result without an official link is not trusted
    if not domain_ok(apply_url, allowed):
        apply_url = src.get("apply", src["url"])
    if notify_url and not domain_ok(notify_url, allowed):
        notify_url = ""
    start = parse_date(j.get("start"))
    docs = [str(d)[:120] for d in (j.get("docs") or []) if str(d).strip()][:15]
    out = {
        "org": str(j.get("org") or src["name"])[:40],
        "post": str(j["post"])[:160],
        "postTa": str(j.get("postTa") or "")[:160],
        "total": str(j.get("total") or "")[:30],
        "start": start.isoformat() if start else "",
        "last": last.isoformat(),
        "qual": str(j.get("qual") or "")[:200],
        "age": str(j.get("age") or "")[:120],
        "fee": str(j.get("fee") or "")[:120],
        "docs": docs,
        "notifyUrl": notify_url,
        "applyUrl": apply_url,
        "note": str(j.get("note") or "")[:200],
        "cat": src["cat"],
        "siteId": src.get("siteId", ""),
        "source": "auto-" + how,
        "added": TODAY.isoformat(),
    }
    out["id"] = "a" + hashlib.md5(job_key(out).encode()).hexdigest()[:10]
    return out


# ------------------------------------------------------------------ main
def main():
    cfg = load_json(CONFIG_PATH, {})
    sources = [s for s in load_json(SOURCES_PATH, []) if s.get("enabled", True)]
    old = load_json(JOBS_PATH, {"vacs": []})
    seen = load_json(SEEN_PATH, {"links": {}})
    if seen.get("v") != 2:  # reset old-format list (v1 marked links seen without reading them)
        seen = {"v": 2, "links": {}}
    allowed = cfg.get("allowed_domains", ["gov.in", "nic.in"])
    max_chars = cfg.get("max_text_chars", 12000)
    max_new = cfg.get("max_new_links_per_source", 4)

    # keep old jobs that are still open
    jobs = {}
    for j in old.get("vacs", []):
        d = parse_date(j.get("last"))
        if d and d >= TODAY:
            jobs[job_key(j)] = j
    log(f"Kept {len(jobs)} open jobs from previous run")

    ai = AI(cfg)
    report = []
    first_run = not seen["links"]

    for src in sources:
        log(f"== {src['name']} ==")
        added = 0
        status = "ok"
        # 1) read official page links
        try:
            links = [(t, h) for t, h in page_links(src["url"]) if looks_like_job(t, h)]
            new = [(t, h) for t, h in links if h not in seen["links"]]
            log(f"  {len(links)} job-like links, {len(new)} new")
            if not ai.providers:
                log("  (no AI key - links kept for next run)")
                new = []
            elif first_run:
                # first ever run: old backlog is skipped, only the top links are read
                for t, h in new[max_new:]:
                    seen["links"][h] = TODAY.isoformat()
            for t, h in new[:max_new]:
                try:
                    text = doc_text(h, max_chars)
                    if len(text) < 200:
                        seen["links"][h] = TODAY.isoformat()
                        continue
                    try:
                        res = ai.ask_json(extract_prompt(src, t, h, text))
                    except AIError as e:
                        log("  AI not available now, will retry next run:", e)
                        break
                    seen["links"][h] = TODAY.isoformat()
                    for j in (res.get("jobs", []) if isinstance(res, dict) else res):
                        cj = clean_job(j, src, allowed, "page")
                        if cj:
                            if not cj["notifyUrl"]:
                                cj["notifyUrl"] = h if domain_ok(h, allowed) else src["url"]
                            jobs[job_key(cj)] = {**jobs.get(job_key(cj), {}), **cj}
                            added += 1
                except Exception as e:
                    seen["links"][h] = TODAY.isoformat()
                    log("  link failed:", h, e)
        except Exception as e:
            status = f"page not readable ({type(e).__name__})"
            log("  page failed:", e)

        # 2) Gemini + Google Search (finds jobs even when the site blocks us / uses JavaScript)
        if cfg.get("use_google_search", True) and ai.providers:
            try:
                res = ai.ask_json(search_prompt(src), use_search=True)
                for j in (res.get("jobs", []) if isinstance(res, dict) else res):
                    cj = clean_job(j, src, allowed, "search")
                    if cj and job_key(cj) not in jobs:
                        jobs[job_key(cj)] = cj
                        added += 1
            except Exception as e:
                log("  search failed:", e)
        report.append({"source": src["name"], "status": status, "added": added})

    # trim seen list (keep 4000 newest)
    if len(seen["links"]) > 4000:
        seen["links"] = dict(sorted(seen["links"].items(), key=lambda x: x[1])[-4000:])

    vacs = sorted(jobs.values(), key=lambda j: j["last"])
    out = {
        "app": "WebSiteMaster",
        "version": 1,
        "updated": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
        "count": len(vacs),
        "vacs": vacs,
        "report": report,
        "ai_calls": ai.calls,
    }
    save_json(JOBS_PATH, out)
    save_json(SEEN_PATH, seen)
    log(f"DONE: {len(vacs)} open jobs written. AI calls used: {ai.calls}")
    if not ai.providers:
        log("WARNING: GEMINI_API_KEY secret is empty. Add it in Settings > Secrets and variables > Actions.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("FATAL:", e)
        sys.exit(1)
