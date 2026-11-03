from __future__ import annotations

import re

from ..assessments_bank import FIELDS
from ..errors import ApiError, not_found
from ..security import EMAIL_RE, hash_password, validate_password, verify_password


def public_user(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "status": u["status"]}


def clean_text(v, field, lo, hi):
    if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
        raise ApiError("INVALID_INPUT", f"{field.replace('_', ' ').capitalize()} must be {lo}-{hi} characters.", 400, {"field": field})
    return re.sub(r"\s+", " ", v.strip())


class AuthService:
    def __init__(self, ctx):
        self.c = ctx

    def register(self, name, email, password, role, company=None, field=None):
        name = clean_text(name, "name", 2, 80)
        email = (email or "").strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 254:
            raise ApiError("INVALID_EMAIL", "Enter a valid e-mail address.", 400, {"field": "email"})
        validate_password(password)
        if role not in ("CANDIDATE", "RECRUITER"):
            raise ApiError("INVALID_ROLE", "Choose Candidate or Recruiter.", 400, {"field": "role"})
        if role == "RECRUITER":
            company = clean_text(company, "company", 2, 80)
        else:
            field = field or FIELDS[0]
            if field not in FIELDS:
                raise ApiError("INVALID_FIELD", "Choose one of the listed fields.", 400, {"field": "field"})
        if self.c.users.find_by_email(email):
            raise ApiError("EMAIL_TAKEN", "An account with this e-mail already exists.", 409, {"field": "email"})
        uid = self.c.users.create(name, email, hash_password(password), role)
        if role == "CANDIDATE":
            self.c.candidates.create(uid, field)
        else:
            self.c.recruiters.create(uid, company)
        return self._session(self.c.users.find(uid))

    def login(self, email, password, ip="?"):
        email = (email or "").strip().lower()
        key = f"{email}|{ip}"
        self.c.app.throttle.check(key)
        u = self.c.users.find_by_email(email)
        if not u or not isinstance(password, str) or not verify_password(password, u["password_hash"]):
            self.c.app.throttle.fail(key)
            raise ApiError("BAD_CREDENTIALS", "Incorrect e-mail or password.", 401)
        if u["status"] != "ACTIVE":
            raise ApiError("ACCOUNT_" + u["status"], "This account has been " + u["status"].lower() + ". Contact an administrator.", 403)
        self.c.app.throttle.reset(key)
        return self._session(u)

    def social_login(self, provider, email, name, role, company=None, field=None):
        """Stand-in for OAuth: signs in or creates the account for a verified provider e-mail.
        Swap the controller call for a real Google/Apple/LinkedIn code exchange once client IDs exist."""
        import secrets
        if provider not in ("google", "apple", "linkedin"):
            raise ApiError("INVALID_PROVIDER", "Unsupported sign-in provider.", 400)
        email = (email or "").strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 254:
            raise ApiError("INVALID_EMAIL", "Enter a valid e-mail address.", 400, {"field": "email"})
        u = self.c.users.find_by_email(email)
        if u:
            if u["status"] != "ACTIVE":
                raise ApiError("ACCOUNT_" + u["status"], "This account has been " + u["status"].lower() + ". Contact an administrator.", 403)
            return self._session(u)
        if role not in ("CANDIDATE", "RECRUITER"):
            raise ApiError("INVALID_ROLE", "Choose Candidate or Recruiter.", 400)
        return self.register(name or email.split("@")[0].replace(".", " ").title(), email, secrets.token_urlsafe(18) + "aA1", role, company or "Independent", field)

    def demo_login(self, role):
        if not self.c.cfg.seed_demo:
            raise ApiError("DEMO_DISABLED", "Demo accounts are disabled.", 403)
        email = {"CANDIDATE": "alex.chen@proofhire.dev", "RECRUITER": "nova@techcorp.com", "ADMIN": "admin@proofhire.dev"}.get(role)
        u = self.c.users.find_by_email(email) if email else None
        if not u or u["status"] != "ACTIVE":
            raise not_found("Demo account")
        return self._session(u)

    def _session(self, u):
        return {"token": self.c.app.tokens.issue(u["id"], u["role"]), "user": public_user(u)}


class ProfileService:
    def __init__(self, ctx):
        self.c = ctx

    def get(self, cid):
        p = self.c.candidates.find(cid)
        if not p:
            raise not_found("Profile")
        return {"id": p["id"], "name": p["name"], "email": p["email"], "bio": p["bio"], "skills": p["skills"],
                "portfolio_links": p["portfolio_links"], "field": p["field"],
                "assessment": self.c.assessments.required_status(cid)}

    def update(self, cid, data):
        p = self.c.candidates.find(cid)
        bio = data.get("bio", p["bio"])
        if not isinstance(bio, str) or len(bio) > 600:
            raise ApiError("INVALID_INPUT", "Bio must be at most 600 characters.", 400, {"field": "bio"})
        skills = data.get("skills", p["skills"])
        if not isinstance(skills, list) or len(skills) > 30:
            raise ApiError("INVALID_INPUT", "Add at most 30 skills.", 400, {"field": "skills"})
        seen, clean = set(), []
        for s in skills:
            if not isinstance(s, str) or not 1 <= len(s.strip()) <= 40:
                raise ApiError("INVALID_INPUT", "Each skill must be 1-40 characters.", 400, {"field": "skills"})
            if s.strip().lower() not in seen:
                seen.add(s.strip().lower())
                clean.append(s.strip())
        links = data.get("portfolio_links", p["portfolio_links"])
        if not isinstance(links, list) or len(links) > 10 or any(not isinstance(x, str) or not re.match(r"^https?://\S{3,300}$", x.strip()) for x in links):
            raise ApiError("INVALID_INPUT", "Portfolio links must be http(s) URLs (max 10).", 400, {"field": "portfolio_links"})
        field = data.get("field", p["field"])
        if field not in FIELDS:
            raise ApiError("INVALID_FIELD", "Choose one of the listed fields.", 400, {"field": "field"})
        name = data.get("name")
        if name is not None:
            name = clean_text(name, "name", 2, 80)
            self.c.conn.execute("UPDATE users SET name=? WHERE id=?", (name, cid))
        self.c.candidates.update_profile(cid, bio.strip(), clean, [x.strip() for x in links], field)
        return self.get(cid)
