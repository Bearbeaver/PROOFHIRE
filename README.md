# ProofHire

Skills-based recruitment: candidates submit verifiable evidence (GitHub repositories, portfolios, certificates), an
AI engine (the **ProofScore Engine**) scores it out of 10 across seven dimensions with annotated feedback, and recruiters
search and review candidates by evidence. Built from the CSC 312 analysis and design documents.

## Quick start

```bash
pip install -r requirements.txt
python run_all.py            # engine on :5001 + web app on :5000
```

Open http://127.0.0.1:5000. The first start trains the scoring model (about 30 seconds); later starts are instant.
Everything runs offline with the fictional demo data. Real public GitHub repositories are analysed live
(set `GITHUB_TOKEN` to raise GitHub's 60 requests/hour anonymous limit).

**Demo accounts** (password `demo1234`; use the "Continue with demo account" button): candidate `alex.chen@proofhire.dev`,
recruiter `nova@techcorp.com`, admin `admin@proofhire.dev` (sign-in link at the bottom of the landing page).
Set `PROOFHIRE_SEED_DEMO=0` for any real deployment, otherwise those accounts exist with a known password.

Try the improvement loop: as Alex, resubmit "Queuely" with `https://github.com/alexchen/queuely-v2` and watch the score rise.
Demo repositories with recorded signals: `alexchen/queuely`, `alexchen/queuely-v2`, `priyapatel/loomly`, `marcuswebb/streamline`,
`sofiareyes/ledgerly`, `danielkim/visionkit`, `demo-user/todo-list`, `demo-user/api-starter`.

## Architecture (design Section 8)

```
 Browser (vanilla-JS SPA, no build step)
        | REST + JWT
 Flask web app  -- controllers -> services -> repositories (DAO) -> SQLite
        |   AccessControlFilter (JWT + role + ownership)      schema.sql (PostgreSQL-portable)
        |   ScoringQueue (worker, retry with back-off, durable: re-enqueued from DB on start)
        |   ProofScoreClient (Strategy: Http | Mock)
        | HTTP + shared key
 ProofScore Engine (Flask)  -- signals (GitHub API / SSRF-safe page fetch) -> features -> scikit-learn model -> feedback
```

| Design element | Where |
|---|---|
| Submission state machine PENDING→SCORED→RESUBMITTED→SCORED, QUEUED on engine failure | `backend/services/submissions.py` |
| Resubmission limit is configuration (admin Settings), not code | `SystemConfig` table |
| Engine down: save, queue, retry with back-off, alert admin, admin can re-queue | `ScoringService.process`, `scoring/queue.py` |
| RBAC, suspended users rejected at token validation, ownership checks | `backend/access_control.py` |
| Hashed (scrypt, salted) passwords, short-lived JWTs, login throttling | `backend/security.py` |
| Admin actions and their audit entry written in one transaction | `AdminService` |
| Certificates served through signed, time-limited URLs | `FileStore`, `/api/files/<token>` |
| Engine never receives name or e-mail (bias-reduced, explainable) | `ScoringService.build_bundle` |
| Standardised per-field assessments (pass mark 75%, valid 180 days) that keep a ProofScore *verified*; unverified scores show as **provisional** to recruiters | `backend/services/assessments.py` |
| Screens S1-S11, candidate (green "code" theme), recruiter (blue "corporate"), admin (slate), light/dark, animations | `backend/static/` |

## The AI, honestly

* The model is a scikit-learn regressor (ridge baseline vs random forest vs gradient boosting, compared by cross-validated MAE/RMSE/R²)
  over about 45 measured features (tests, CI, README structure, size, activity, field-keyword overlap, ...). Feedback sentences are
  rule-based and tied to measured facts, shown under "What was measured".
* **It is trained on a synthetic placeholder dataset** (`engine/synthetic.py`) because the human-labelled dataset from the proposal does not
  exist yet. Its cross-validated R² only says it reproduces the rubric used to generate the labels, not that it agrees with human
  evaluators. Drop real labels in `engine/data/labelled_projects.csv` (columns in `engine/synthetic.py`) and run `python -m engine.train`.
  The admin dashboard shows which model and training data are live.
* CodeBERT is **not** included. Features come from repository structure and text, not code embeddings. `engine/features.py` is where embeddings would plug in.
* Certificates are judged on issuer/verification-link metadata only; file contents are not machine-verified.

## Tests

```bash
python -m unittest tests.test_backend tests.test_engine     # 46 tests
python run_all.py &  python tests/e2e_browser.py            # 58 browser checks (needs: pip install playwright && playwright install chromium)
```

## Honest limitations / before production

SQLite and the in-process queue suit one server; swap in PostgreSQL (the repository layer isolates all SQL) and a broker (RabbitMQ/SQS)
behind `ScoringQueue`'s interface to scale. Use a production WSGI server (gunicorn/waitress) behind HTTPS, set `PROOFHIRE_SECRET`, `ENGINE_KEY`,
`GITHUB_TOKEN`, turn demo data off, and replace the in-memory login throttle with a shared store. The SSRF guard resolves DNS before connecting
(a determined DNS-rebinding attack is not covered). Uploaded files are stored on local disk. The UI is vanilla JS rather than React because
the build tooling could not be installed where this was built; the REST API is framework-neutral if you want to port it.
