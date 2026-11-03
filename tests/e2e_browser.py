"""End-to-end browser test (Playwright + headless Chromium) against a RUNNING app on :5000 with the demo data.

    python run_all.py &            # in another terminal
    python tests/e2e_browser.py

Exercises real user journeys through the UI and the real engine (demo repositories are scored from fixtures).
Screenshots are written to tests/screenshots/.
"""
import os
import sys
import time

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.assessments_bank import BANK  # noqa: E402

BASE = os.environ.get("BASE", "http://127.0.0.1:5000")
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SHOTS, exist_ok=True)
problems, checks = [], []


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.route("**/*", lambda route: route.abort() if "fonts.g" in route.request.url else route.continue_())
        page = ctx.new_page()
        page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("dialog", lambda d: d.accept())

        def clean(name):
            """No leaked JS values (undefined/null/NaN/[object ...]/stray 'false') anywhere in the visible page text."""
            page.wait_for_timeout(400)
            txt = page.inner_text("body")
            import re
            bad = re.findall(r"\[object \w+\]|\bundefined\b|\bNaN\b|\bnull\b|Something went wrong|^false$|^true$", txt, re.M)
            ok(f"no leaked JS values on {name}", not bad, str(bad[:3]))

        def waitok(name, fn, timeout=8.0):
            end, val = time.time() + timeout, False
            while time.time() < end:
                try:
                    val = fn()
                except Exception:
                    val = False
                if val:
                    break
                page.wait_for_timeout(150)
            ok(name, val)

        # ---------------------------------------------------------------- public
        print("Public pages")
        page.goto(BASE + "/")
        expect(page.get_by_role("heading", name="Recruit on evidence, not resumes.")).to_be_visible()
        shot(page, "01_landing")
        page.goto(BASE + "/#/candidate/portfolio")
        ok("protected route redirects to landing when logged out", page.get_by_role("heading", name="Recruit on evidence, not resumes.").is_visible())

        page.get_by_role("link", name="Continue as candidate").click()
        page.get_by_role("button", name="Log in").click()
        ok("empty login shows inline field errors", page.get_by_text("Enter a valid email address.").is_visible() and page.get_by_text("Enter your password.").is_visible())
        page.fill("#email", "alex.chen@proofhire.dev")
        page.fill("#password", "wrong-password")
        page.get_by_role("button", name="Log in").click()
        expect(page.get_by_text("Incorrect e-mail or password.")).to_be_visible()
        ok("wrong password rejected", True)
        shot(page, "02_login_error")

        # registration with validation errors then success
        page.get_by_role("link", name="Create an account").click()
        page.fill("#name", "Zed Tester")
        page.fill("#email", "alex.chen@proofhire.dev")
        page.fill("#password", "longenough1")
        page.get_by_role("button", name="Create account").click()
        expect(page.get_by_text("An account with this e-mail already exists.")).to_be_visible()
        ok("duplicate e-mail error shown next to the field", True)
        page.fill("#email", f"zed{int(time.time())}@example.com")
        page.select_option("#field", "Frontend Engineering")
        page.get_by_role("button", name="Create account").click()
        expect(page.get_by_role("heading", name="Zed Tester")).to_be_visible()
        ok("registration logs the new candidate in", True)
        ok("new candidate sees provisional banner (assessment not taken)", page.get_by_text("Take the Frontend Engineering assessment").is_visible())
        ok("empty portfolio shows add-evidence card", page.get_by_role("link", name="Add evidence").count() >= 1)
        shot(page, "03_new_candidate_empty")
        page.locator("button[aria-label='Account menu']").click()
        page.get_by_role("menuitem", name="Log out").click()

        # ---------------------------------------------------------------- candidate demo
        print("Candidate journey")
        page.goto(BASE + "/#/login/candidate")
        page.get_by_role("button", name="Continue with demo account").click()
        expect(page.get_by_role("heading", name="Alex Chen")).to_be_visible()
        ok("demo candidate sees seeded exhibits", page.locator("a.exhibit").count() == 2)
        ok("assessment-expiring banner shown", page.get_by_text("expires on").is_visible())
        clean("candidate portfolio")
        shot(page, "04_candidate_portfolio")

        # add evidence: client-side validation first
        page.get_by_role("link", name="Add evidence").first.click()
        page.get_by_role("button", name="Submit for scoring").click()
        ok("form blocks invalid input with inline errors", page.get_by_text("Give the exhibit a title").is_visible() and page.get_by_text("Enter a GitHub repository link").is_visible())
        page.fill("#title", "Queuely v2 (tests and docs added)")
        page.fill("#url0", "https://github.com/alexchen/queuely-v2")
        page.fill("#desc0", "Added tests, CI and architecture notes")
        shot(page, "05_add_evidence")
        page.get_by_role("button", name="Submit for scoring").click()
        expect(page.get_by_role("heading", name="Queuely v2 (tests and docs added)")).to_be_visible()
        ok("submission shows scoring progress immediately", page.get_by_text("Scoring").first.is_visible())
        expect(page.get_by_text("Recommended actions")).to_be_visible(timeout=40000)
        ok("score arrives via polling without reload", page.locator("svg[aria-label^='ProofScore']").first.is_visible())
        score_label = page.locator("svg[aria-label^='ProofScore']").first.get_attribute("aria-label")
        print("    scored:", score_label)
        ok("radar + 7 sub-score bars rendered", page.locator("svg[aria-label^='Score breakdown']").count() == 1 and page.locator("div.bar").count() == 7)
        ok("improvement cycle: resubmit button shows remaining count", page.get_by_role("link", name="Resubmit improved evidence (2 of 2 remaining)").is_visible())
        clean("scored exhibit page")
        shot(page, "06_exhibit_scored")

        # resubmit the seeded Queuely exhibit and watch the score history grow
        page.get_by_role("link", name="Portfolio").first.click()
        page.locator("a.exhibit", has_text="Queuely - Distributed").click()
        expect(page.locator("table tbody tr")).to_have_count(2)      # seeded history: attempts #1 and #2
        before = 2
        page.get_by_role("link", name="Resubmit improved evidence (1 of 2 remaining)").click()
        page.fill("#url0", "https://github.com/alexchen/queuely-v2")
        page.get_by_role("button", name="Resubmit for scoring").click()
        expect(page.get_by_role("button", name="Resubmit", exact=True)).to_be_visible()  # confirmation dialog states the consequence
        ok("resubmit asks for confirmation and states what is left", page.get_by_text("You will have 0 left afterwards.").is_visible())
        page.get_by_role("button", name="Resubmit", exact=True).click()
        expect(page.locator("table tbody tr")).to_have_count(before + 1, timeout=40000)
        ok("history shows the new attempt", True)
        ok("limit reached: button disabled with the reason in text", page.get_by_text("You have used all 2 resubmissions").is_visible())
        shot(page, "07_resubmitted_limit")

        # assessments
        page.get_by_role("link", name="Assessments").first.click()
        waitok("required assessment listed first", lambda: page.locator("h2").first.inner_text() == "Backend Engineering")
        clean("assessments")
        shot(page, "08_assessments")
        page.get_by_role("link", name="Retake").first.click()
        qs = page.locator(".q")
        waitok("8 questions shown", lambda: qs.count() == 8)
        ok("submit disabled until all answered", page.locator("#submit-quiz").is_disabled())
        bank = {q["q"]: q for q in BANK["Backend Engineering"]}
        for i in range(qs.count()):
            text = qs.nth(i).locator("legend").inner_text().split(". ", 1)[1]
            qs.nth(i).locator("input[type=radio]").nth(bank[text]["answer"]).check()
        shot(page, "09_quiz_answered")
        page.locator("#submit-quiz").click()
        expect(page.get_by_text("PASSED")).to_be_visible()
        ok("passing the assessment shows result", page.get_by_text("8 / 8 correct").is_visible())
        page.get_by_role("link", name="Portfolio").first.click()
        ok("banner gone once assessment is valid", page.get_by_text("expires on").count() == 0)

        # jobs, messages, profile
        page.get_by_role("link", name="Job listings").first.click()
        waitok("job listings show skill match", lambda: page.get_by_text("skill match").count() >= 1)
        page.fill("#jq", "Data Engineer")
        expect(page.get_by_role("heading", name="Data Engineer")).to_be_visible()
        page.get_by_role("link", name="Messages").first.click()
        waitok("recruiter message visible", lambda: page.get_by_text("Nimbus Labs").first.is_visible())
        page.get_by_role("link", name="Profile").first.click()
        page.fill("#skills", "Go, gRPC, Kafka")
        page.get_by_role("button", name="Save profile").click()
        expect(page.get_by_text("Profile saved.")).to_be_visible()
        ok("profile saved", True)

        # notifications bell
        page.locator("button[aria-label^='Notifications']").click()
        waitok("notification for the new score", lambda: page.get_by_text("was scored").first.is_visible())
        page.keyboard.press("Escape")
        page.locator("button[aria-label='Account menu']").click()
        page.get_by_role("menuitem", name="Log out").click()

        # ---------------------------------------------------------------- recruiter
        print("Recruiter journey")
        page.goto(BASE + "/#/login/recruiter")
        page.get_by_role("button", name="Continue with demo account").click()
        expect(page.get_by_role("heading", name="Candidate search")).to_be_visible()
        try:
            expect(page.locator("article.result").first).to_be_visible(timeout=15000)
        except AssertionError:
            print("DEBUG main text:", page.inner_text("main")[:600].replace("\n", " | "))
            print("DEBUG filters:", page.evaluate("localStorage.getItem('ph_filters')"))
            shot(page, "debug_recruiter")
            raise
        n_all = page.locator("article.result").count()
        scores = [float(x) for x in page.locator("article.result .score-pill").evaluate_all("els => els.map(e => e.childNodes[0].textContent)")]
        ok("results sorted by ProofScore, highest first", scores == sorted(scores, reverse=True), str(scores))
        waitok("provisional candidates flagged", lambda: page.get_by_text("Provisional").count() >= 2)
        clean("recruiter search")
        shot(page, "10_recruiter_search")
        page.fill("#skill", "airflow")
        expect(page.locator("article.result")).to_have_count(1)
        ok("skill filter works", page.locator("article.result").first.inner_text().startswith("Marcus Webb"))
        page.fill("#skill", "")
        expect(page.locator("article.result")).to_have_count(n_all)
        page.locator("#min").fill("6")
        waitok("min-score slider filters", lambda: 0 < page.locator("article.result").count() < n_all)
        page.reload()
        waitok("filters persist between visits", lambda: page.locator("#min-out").inner_text() == "6.0")
        page.get_by_role("button", name="Clear filters").first.click()
        page.get_by_role("link", name="Alex Chen").first.click()
        expect(page.get_by_role("heading", name="Alex Chen")).to_be_visible()
        waitok("profile shows breakdown but no improvement advice", lambda: page.get_by_text("Recommended actions").count() == 0 and page.locator("div.bar").count() >= 7)
        clean("recruiter candidate profile")
        shot(page, "11_recruiter_profile")
        page.get_by_role("button", name="Shortlisted").or_(page.get_by_role("button", name="Shortlist")).first.click()
        page.get_by_role("button", name="Contact").click()
        page.fill("#msg", "short")
        page.get_by_role("button", name="Send message").click()
        expect(page.get_by_text("Message must be 10-1000 characters.")).to_be_visible()
        ok("too-short message rejected with a clear error", True)
        page.fill("#msg", "Hi Alex, we loved Queuely and would like to talk about a role.")
        page.get_by_role("button", name="Send message").click()
        expect(page.get_by_text("Message sent.")).to_be_visible()
        ok("contact sent", True)
        page.get_by_role("link", name="Shortlist").first.click()
        waitok("shortlist tray lists candidates", lambda: page.locator("article.result").count() >= 2)
        page.get_by_role("link", name="Jobs").first.click()
        page.fill("#jt", "Site Reliability Engineer")
        page.fill("#jd", "Keep the platform running.")
        page.get_by_role("button", name="Post job").click()
        expect(page.get_by_role("heading", name="Site Reliability Engineer")).to_be_visible()
        ok("recruiter can post a job", True)
        # theme toggle (dark/light)
        page.get_by_role("link", name="Candidate search").first.click()
        mode0 = page.evaluate("document.documentElement.dataset.mode")
        page.locator("#mode-btn").click()
        mode1 = page.evaluate("document.documentElement.dataset.mode")
        ok("light/dark toggle flips the theme", mode0 != mode1)
        shot(page, "12_recruiter_" + mode1)
        page.locator("#mode-btn").click()
        page.locator("button[aria-label='Account menu']").click()
        page.get_by_role("menuitem", name="Log out").click()

        # ---------------------------------------------------------------- admin
        print("Admin journey")
        page.goto(BASE + "/#/login/admin")
        page.get_by_role("button", name="Continue with demo account").click()
        expect(page.get_by_role("heading", name="Control room")).to_be_visible()
        waitok("dashboard shows engine up and model", lambda: page.get_by_text("Engine up").is_visible() and page.get_by_text("gradient_boosting").first.is_visible())
        waitok("per-day chart rendered", lambda: page.locator("svg[aria-label^='Submissions per day']").count() == 1)
        clean("admin dashboard")
        shot(page, "13_admin_dashboard")
        page.get_by_role("link", name="Registers").first.click()
        page.fill("#rq", "Marcus")
        expect(page.locator("tbody tr")).to_have_count(1)
        page.get_by_role("button", name="Suspend").click()
        page.get_by_role("button", name="Suspend", exact=True).last.click()
        waitok("reason is required to suspend", lambda: page.get_by_text("Please give a short reason").is_visible())
        page.fill("#reason-box", "Evidence could not be verified")
        page.get_by_role("button", name="Suspend", exact=True).last.click()
        expect(page.locator("tbody tr .chip.bad")).to_have_text("suspended")
        ok("account suspended", True)
        page.get_by_role("tab", name="Submissions").click()
        expect(page.get_by_text("Flag: Portfolio text looks copied")).to_be_visible()
        clean("admin registers")
        shot(page, "14_admin_registers")
        page.get_by_role("button", name="Dismiss flag").click()
        page.fill("#reason-box", "Checked, original work")
        page.get_by_role("button", name="Dismiss flag", exact=True).last.click()
        page.get_by_role("link", name="Audit log").first.click()
        waitok("audit log has both actions", lambda: page.get_by_text("SUSPEND_USER").is_visible() and page.get_by_text("DISMISS_FLAG").is_visible())
        shot(page, "15_admin_audit")
        page.get_by_role("link", name="Settings").first.click()
        page.fill("#maxr", "3")
        page.get_by_role("button", name="Save").click()
        page.get_by_role("button", name="Apply").click()
        expect(page.get_by_text("Saved.")).to_be_visible()
        ok("config change applied", True)
        page.locator("button[aria-label='Account menu']").click()
        page.get_by_role("menuitem", name="Log out").click()

        # suspended user is locked out
        page.goto(BASE + "/#/login/candidate")
        page.fill("#email", "marcus@example.com")
        page.fill("#password", "demo1234")
        page.get_by_role("button", name="Log in").click()
        expect(page.get_by_text("This account has been suspended")).to_be_visible()
        ok("suspended account cannot log in", True)

        # ---------------------------------------------------------------- motion
        print("Motion")
        page.goto(BASE + "/#/login/candidate")
        page.get_by_role("button", name="Continue with demo account").click()
        expect(page.get_by_role("heading", name="Alex Chen")).to_be_visible()
        names = page.evaluate("[...document.querySelectorAll('main > *')].map(e => getComputedStyle(e).animationName)")
        ok("views animate in when motion is allowed", any(n == "rise" for n in names), str(names))
        page.locator("a.exhibit").first.click()
        expect(page.locator("svg[aria-label^='ProofScore']").first).to_be_visible()
        label = page.locator("svg[aria-label^='ProofScore']").first.get_attribute("aria-label")
        final = label.split("ProofScore ")[1].split(" out")[0]
        waitok("score ring counts up to the real value", lambda: page.locator(".ring-text").first.text_content() == final, 4)
        ok("ring arc and radar use reveal animations", page.evaluate("getComputedStyle(document.querySelector('.ring-arc')).animationName") == "draw-ring"
           and page.evaluate("getComputedStyle(document.querySelector('.radar-shape')).animationName") == "radar-in")
        page.locator("button[aria-label='Account menu']").click()
        page.get_by_role("menuitem", name="Log out").click()
        rm = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
        rm.route("**/*", lambda route: route.abort() if "fonts.g" in route.request.url else route.continue_())
        rp = rm.new_page()
        rp.goto(BASE + "/#/login/candidate")
        rp.get_by_role("button", name="Continue with demo account").click()
        expect(rp.get_by_role("heading", name="Alex Chen")).to_be_visible()
        rnames = rp.evaluate("[...document.querySelectorAll('main > *, .card.exhibit')].map(e => getComputedStyle(e).animationName)")
        ok("prefers-reduced-motion disables entrance animations", all(n == "none" for n in rnames), str(set(rnames)))
        rp.locator("a.exhibit").first.click()
        expect(rp.locator(".ring-text").first).to_be_visible()
        ok("reduced motion shows the final score immediately", rp.locator(".ring-text").first.text_content() == rp.locator("svg[aria-label^='ProofScore']").first.get_attribute("aria-label").split("ProofScore ")[1].split(" out")[0])
        rm.close()

        # ---------------------------------------------------------------- mobile + a11y basics
        print("Responsive / accessibility")
        m = browser.new_context(viewport={"width": 390, "height": 800})
        m.route("**/*", lambda route: route.abort() if "fonts.g" in route.request.url else route.continue_())
        mp = m.new_page()
        mp.goto(BASE + "/#/login/candidate")
        mp.get_by_role("button", name="Continue with demo account").click()
        expect(mp.get_by_role("heading", name="Alex Chen")).to_be_visible()
        overflow = mp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
        ok("no horizontal scroll on a 390px phone", not overflow)
        shot(mp, "16_mobile_portfolio")
        unlabeled = mp.evaluate("[...document.querySelectorAll('input,select,textarea')].filter(e => !e.labels.length && !e.getAttribute('aria-label') && !e.closest('label')).length")
        ok("every form control has a label", unlabeled == 0, str(unlabeled))
        browser.close()

    print()
    bad = [n for n, c in checks if not c]
    print(f"{len(checks) - len(bad)}/{len(checks)} checks passed")
    import re
    def expected(p):  # intentional negative tests produce 4xx responses, which Chromium logs as console errors
        m = re.search(r"status of (\d{3})", p)
        return "ERR_FAILED" in p or "fonts" in p or (m and m.group(1).startswith("4"))
    real = [p for p in problems if not expected(p)]
    print("browser console/page errors:", real or "none")
    return 1 if bad or real else 0


if __name__ == "__main__":
    sys.exit(run())
