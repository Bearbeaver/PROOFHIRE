"""Standardised skills assessments, one per field. Correct answers never leave the server."""

# Every tech role a candidate can register under, grouped for the sign-up picker.
# Each role is assessed against the nearest of the three question banks (its "track").
ROLE_GROUPS = {
    "Software Engineering": {"track": "Backend Engineering", "roles": ["Backend Engineering", "Full-Stack Engineering", "Mobile Engineering (iOS & Android)", "Embedded & Firmware Engineering", "Game Development", "Blockchain & Web3 Engineering", "QA & Test Automation"]},
    "Frontend & Design": {"track": "Frontend Engineering", "roles": ["Frontend Engineering", "UI & UX Design", "Product Design", "Technical Writing"]},
    "Data & AI": {"track": "Data & ML Engineering", "roles": ["Data & ML Engineering", "Data Science", "Data Analytics", "Data Engineering", "AI & LLM Engineering", "Computer Vision Engineering"]},
    "Cloud, Infra & Security": {"track": "Backend Engineering", "roles": ["DevOps Engineering", "Cloud Architecture", "Site Reliability Engineering", "Platform Engineering", "Cybersecurity Analyst", "Penetration Testing", "Network Engineering", "Database Administration", "IT Support & Systems Administration"]},
    "Product & Leadership": {"track": "Frontend Engineering", "roles": ["Product Management", "Technical Project Management", "Business Analysis", "Engineering Management", "Solutions Architecture"]},
}
FIELDS = [r for g in ROLE_GROUPS.values() for r in g["roles"]]
TRACK = {r: g["track"] for g in ROLE_GROUPS.values() for r in g["roles"]}


def _q(qid, q, options, answer, topic):
    return {"id": qid, "q": q, "options": options, "answer": answer, "topic": topic}


BANK = {
    "Backend Engineering": [
        _q("be1", "What does 'at-least-once delivery' guarantee in a message queue?",
           ["A message is never duplicated", "A message is delivered, but may be processed more than once", "Messages always arrive in order", "Messages are encrypted in transit"], 1, "Messaging"),
        _q("be2", "Which HTTP status code best fits a request with a valid token but insufficient permissions?",
           ["401", "403", "404", "422"], 1, "HTTP & REST"),
        _q("be3", "What is the main purpose of a dead-letter queue?",
           ["Speed up serialization", "Hold messages that repeatedly failed processing for inspection", "Load-balance consumers", "Encrypt queue contents"], 1, "Messaging"),
        _q("be4", "A query filtering on `WHERE email = ?` is slow on a large table. The most direct fix is to:",
           ["Add an index on email", "Increase the connection pool timeout", "Select all columns", "Disable foreign keys"], 0, "Databases"),
        _q("be5", "Which is the safest way to store user passwords?",
           ["Encrypt them with a shared key", "Hash with SHA-256 only", "Hash with a salted, adaptive algorithm such as bcrypt/scrypt/argon2", "Store them base64-encoded"], 2, "Security"),
        _q("be6", "An operation is idempotent when:",
           ["It always returns the same status code", "Repeating it has the same effect as performing it once", "It runs in constant time", "It never touches the database"], 1, "HTTP & REST"),
        _q("be7", "Two requests update the same row at the same time and one overwrites the other's change. This is a:",
           ["Deadlock", "Lost update (race condition)", "Cache miss", "N+1 query"], 1, "Concurrency"),
        _q("be8", "What problem does retrying with exponential back-off mainly avoid?",
           ["Memory leaks", "Overloading a struggling service with immediate repeated requests", "SQL injection", "Cross-site scripting"], 1, "Reliability"),
    ],
    "Frontend Engineering": [
        _q("fe1", "Which HTML choice is best for a clickable control that performs an action?",
           ["<div onclick>", "<span role='link'>", "<button>", "<a> without href"], 2, "Accessibility"),
        _q("fe2", "In React, why should list items have a stable `key`?",
           ["To style them", "So React can match items between renders efficiently and correctly", "To make them focusable", "To sort them"], 1, "React"),
        _q("fe3", "Which CSS rule wins when two selectors of equal specificity target the same element?",
           ["The first one in the file", "The last one declared", "The shortest selector", "The one with !important removed"], 1, "CSS"),
        _q("fe4", "What is the best defence against cross-site scripting (XSS) when rendering user text?",
           ["Escape or textContent-encode it; never insert it as raw HTML", "Hide the input field", "Use HTTPS", "Minify the JavaScript"], 0, "Security"),
        _q("fe5", "A browser blocks your page's request to another origin. This is enforced by:",
           ["DNS", "CORS / same-origin policy", "HTTP/2", "The service worker cache"], 1, "Browser"),
        _q("fe6", "Which technique most directly improves initial page load for below-the-fold images?",
           ["Lazy loading", "Inline styles", "Larger images", "Disabling caching"], 0, "Performance"),
        _q("fe7", "`display: flex; justify-content: space-between;` does what to children?",
           ["Stacks them vertically", "Distributes them along the main axis with free space between", "Centres text", "Makes them equal height only"], 1, "CSS"),
        _q("fe8", "What does a `useEffect` with an empty dependency array `[]` do?",
           ["Runs after every render", "Runs once after the first render (and cleans up on unmount)", "Never runs", "Runs before render"], 1, "React"),
    ],
    "Data & ML Engineering": [
        _q("ml1", "A model scores 99% on training data but 70% on unseen data. This is most likely:",
           ["Underfitting", "Overfitting", "Perfect generalisation", "Label noise only"], 1, "Modelling"),
        _q("ml2", "Why must scaling/imputation be fitted on the training split only?",
           ["To save memory", "To avoid data leakage from the test set", "Because test data is smaller", "It makes training faster"], 1, "Validation"),
        _q("ml3", "On a dataset with 1% positives, accuracy is a poor metric because:",
           ["It is hard to compute", "A model predicting all negatives scores 99%", "It ignores true negatives", "It needs probabilities"], 1, "Metrics"),
        _q("ml4", "Recall is defined as:",
           ["TP / (TP + FP)", "TP / (TP + FN)", "TN / (TN + FP)", "(TP + TN) / total"], 1, "Metrics"),
        _q("ml5", "k-fold cross-validation is mainly used to:",
           ["Speed up training", "Estimate generalisation performance more reliably", "Remove outliers", "Increase the dataset size"], 1, "Validation"),
        _q("ml6", "In SQL, which clause filters groups after aggregation?",
           ["WHERE", "HAVING", "ORDER BY", "LIMIT"], 1, "SQL"),
        _q("ml7", "Increasing L2 regularisation strength generally:",
           ["Increases variance", "Reduces model complexity / variance, at the cost of some bias", "Removes features", "Has no effect"], 1, "Modelling"),
        _q("ml8", "A pipeline step must produce the same result when re-run on the same input. This property is:",
           ["Idempotency / determinism", "Sharding", "Normalisation", "Denormalisation"], 0, "Data engineering"),
    ],
}

DURATION_MIN = 10


def bank_for(field):
    return BANK[TRACK.get(field, field)]
