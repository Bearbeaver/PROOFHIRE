"""Collects evidence signals for the ProofScore Engine.

* ``GitHubFetcher``  - public GitHub REST API (set GITHUB_TOKEN to raise the 60 req/h anonymous limit)
* ``FixtureFetcher`` - recorded signals for the fictional demo repositories (works offline)
* ``PageFetcher``    - fetches portfolio pages with SSRF protection (public IPs only, size/redirect limits)

Network failures on GitHub raise ``UpstreamUnavailable`` / ``UpstreamRateLimited`` so the web back end can
queue the submission and retry later (NFR5) instead of unfairly scoring the candidate as if the repo were missing.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlparse

import requests

from .features import page_stats

GITHUB_API = "https://api.github.com"
UA = "ProofHire-Engine/1.0 (+evidence evaluation)"
_GH_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class UpstreamUnavailable(Exception):
    pass


class UpstreamRateLimited(UpstreamUnavailable):
    pass


def parse_github_url(url: str):
    m = _GH_URL.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


# --------------------------------------------------------------------------- SSRF-safe fetching
def is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def safe_get(url: str, timeout: float = 6.0, max_bytes: int = 600_000, max_redirects: int = 3):
    """Return (status, text) or None. Refuses non-http(s), private/loopback targets (also on redirects)."""
    cur = url
    for _ in range(max_redirects + 1):
        p = urlparse(cur)
        if p.scheme not in ("http", "https") or not p.hostname or not is_public_host(p.hostname):
            return None
        try:
            r = requests.get(cur, headers={"User-Agent": UA}, timeout=timeout, stream=True, allow_redirects=False)
        except requests.RequestException:
            return None
        try:
            if r.status_code in (301, 302, 303, 307, 308):
                cur = urljoin(cur, r.headers.get("Location", ""))
                continue
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return r.status_code, ""
            body = r.raw.read(max_bytes, decode_content=True) or b""
            return r.status_code, body.decode(r.encoding or "utf-8", errors="replace")
        finally:
            r.close()
    return None


class PageFetcher:
    def fetch(self, url: str):
        res = safe_get(url)
        if not res or res[0] >= 400:
            return None
        return page_stats(res[1])


# --------------------------------------------------------------------------- GitHub
class GitHubFetcher:
    def __init__(self, token: str | None = None, timeout: float = 6.0, ttl: int = 600):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/vnd.github+json"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        self.timeout, self.ttl = timeout, ttl
        self._cache: dict[str, tuple[float, dict | None]] = {}
        self._lock = threading.Lock()

    def _get(self, path: str, raw: bool = False):
        try:
            headers = {"Accept": "application/vnd.github.raw+json"} if raw else None
            r = self.s.get(GITHUB_API + path, timeout=self.timeout, headers=headers)
        except requests.RequestException as e:
            raise UpstreamUnavailable(f"GitHub unreachable: {e.__class__.__name__}") from e
        if r.status_code in (403, 429) and (r.headers.get("X-RateLimit-Remaining") == "0" or r.status_code == 429):
            raise UpstreamRateLimited("GitHub API rate limit reached")
        if r.status_code >= 500:
            raise UpstreamUnavailable(f"GitHub error {r.status_code}")
        return r

    def repo_signals(self, owner: str, name: str):
        key = f"{owner}/{name}".lower()
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
        sig = self._fetch(owner, name)
        with self._lock:
            self._cache[key] = (time.time(), sig)
        return sig

    def _fetch(self, owner: str, name: str):
        base = f"/repos/{owner}/{name}"
        r = self._get(base)
        if r.status_code in (404, 410, 451, 403):
            return None  # missing, private or blocked: candidate's problem, not ours
        meta = r.json()
        langs = self._get(base + "/languages").json() or {}
        rr = self._get(base + "/readme", raw=True)
        readme = rr.text[:100_000] if rr.status_code == 200 else ""
        paths = []
        branch = meta.get("default_branch", "main")
        tr = self._get(f"{base}/git/trees/{branch}?recursive=1")
        if tr.status_code == 200:
            paths = [t["path"] for t in tr.json().get("tree", []) if t.get("type") == "blob"][:8000]
        commits = 0
        cr = self._get(base + "/commits?per_page=1")
        if cr.status_code == 200:
            m = re.search(r'[?&]page=(\d+)>; rel="last"', cr.headers.get("Link", ""))
            commits = int(m.group(1)) if m else len(cr.json())
        return {
            "found": True, "full_name": meta.get("full_name", f"{owner}/{name}"),
            "description": meta.get("description") or "", "topics": meta.get("topics") or [],
            "stars": meta.get("stargazers_count", 0), "forks": meta.get("forks_count", 0),
            "size_kb": meta.get("size", 0), "languages": langs,
            "license": bool(meta.get("license")), "homepage": bool(meta.get("homepage")),
            "created_at": meta.get("created_at"), "pushed_at": meta.get("pushed_at"),
            "commits": commits, "readme": readme, "paths": paths,
        }


class FixtureFetcher:
    def __init__(self, fixtures: dict):
        self.fixtures = {k.lower(): v for k, v in fixtures.items()}

    def repo_signals(self, owner: str, name: str):
        return self.fixtures.get(f"{owner}/{name}".lower(), "MISS")


class OfflineFetcher:
    """ENGINE_MODE=offline: never touches the network; unknown repos count as unreachable."""

    def repo_signals(self, owner, name):
        return None


class CompositeFetcher:
    """Fixtures first (demo repos), then the live fetcher."""

    def __init__(self, fixtures, live):
        self.fixtures, self.live = fixtures, live

    def repo_signals(self, owner, name):
        if self.fixtures:
            hit = self.fixtures.repo_signals(owner, name)
            if hit != "MISS":
                return hit
        return self.live.repo_signals(owner, name)


def collect(bundle: dict, gh, pages):
    github, portfolio = [], []
    for it in bundle["evidence"]:
        if it["type"] == "GITHUB":
            parsed = parse_github_url(it.get("url", ""))
            github.append(gh.repo_signals(*parsed) if parsed else None)
        elif it["type"] == "PORTFOLIO":
            portfolio.append(pages.fetch(it.get("url", "")))
    return github, portfolio
