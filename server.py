# ============================================================
#  server.py — StartupHive API v2.0
#  Flask + PostgreSQL (trends_db2) + Cloudinary
#  All tables prefixed: startuphive_
#  Deploy: Render (Web Service) | pip install flask flask-cors
#          psycopg2-binary pyjwt bcrypt cloudinary
# ============================================================

from flask import Flask, request, jsonify, g
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import jwt
import datetime
import bcrypt
import cloudinary
import cloudinary.uploader
import re
import json
from functools import wraps

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ──────────────────────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────────────────────
DB_HOST     = "dpg-d70himndiees73dlbeig-a.frankfurt-postgres.render.com"
DB_NAME     = "trends_db2"
DB_USER     = "trends_db2_user"
DB_PASSWORD = "h5NO8WY8nxLF64WSM7jwYZ7b8B7dCOiR"
DB_PORT     = 5432

CLOUDINARY_CLOUD_NAME = "ddusfl7pi"
CLOUDINARY_API_KEY    = "599965682593626"
CLOUDINARY_API_SECRET = "pUcb90_1jtv-rDlHXRRsfDcBK5k"

JWT_SECRET    = "startuphive_v2_secret_xK9pLm3v_2025"
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS  = 30

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
)

# Allowed enum values
STAGES       = ["idea", "pre-seed", "seed", "series-a", "bootstrapped", "growing", "scaling"]
CATEGORIES   = ["AI", "Fintech", "Climate", "Health", "SaaS", "Consumer", "B2B",
                 "Marketplace", "Hardware", "Education", "Developer Tools", "Web3",
                 "Gaming", "Productivity", "Media", "Other"]
ASK_TYPES    = ["funding", "hiring", "partners", "customers", "press", "advice"]
ASK_URGENCY  = ["ongoing", "this-month", "urgent"]
UPDATE_TYPES = ["launch", "traction", "team", "product", "fundraising", "press", "pivot", "other"]
VER_LEVELS   = ["unregistered", "registered", "verified", "audited"]
METRIC_CONF  = ["claimed", "verified", "audited"]


# ──────────────────────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER,
            password=DB_PASSWORD, port=DB_PORT, sslmode="require",
        )
        g.db.cursor_factory = psycopg2.extras.RealDictCursor
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    """Create all startuphive_ tables on first boot."""
    db  = get_db()
    cur = db.cursor()

    ddl = [
        # ── USERS ─────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_users (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(150)  NOT NULL,
            username        VARCHAR(60)   UNIQUE NOT NULL,
            email           VARCHAR(255)  UNIQUE NOT NULL,
            password_hash   VARCHAR(255)  NOT NULL,
            avatar_url      VARCHAR(500),
            bio             TEXT,
            headline        VARCHAR(200),
            website         VARCHAR(500),
            twitter         VARCHAR(100),
            linkedin        VARCHAR(100),
            github          VARCHAR(100),
            is_verified     BOOLEAN       DEFAULT FALSE,
            reputation      INTEGER       DEFAULT 0,
            last_active     TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
            created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── STARTUPS ──────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_startups (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            name                VARCHAR(150)  NOT NULL,
            slug                VARCHAR(180)  UNIQUE NOT NULL,
            tagline             VARCHAR(250),
            logo_url            VARCHAR(500),
            cover_url           VARCHAR(500),
            status              VARCHAR(20)   DEFAULT 'unregistered'
                                    CHECK (status IN ('unregistered','registered','verified','audited','for_sale','inactive')),
            verification_level  VARCHAR(20)   DEFAULT 'unregistered'
                                    CHECK (verification_level IN ('unregistered','registered','verified','audited')),
            stage               VARCHAR(20)   DEFAULT 'idea'
                                    CHECK (stage IN ('idea','pre-seed','seed','series-a','bootstrapped','growing','scaling')),
            categories          TEXT[]        DEFAULT '{}',
            location_based      VARCHAR(150),
            location_reach      JSONB         DEFAULT '["Global"]',
            founded_date        VARCHAR(20),
            team_size           INTEGER       DEFAULT 1,
            demo_url            VARCHAR(500),
            contact_methods     JSONB         DEFAULT '{}',
            is_active           BOOLEAN       DEFAULT TRUE,
            is_featured         BOOLEAN       DEFAULT FALSE,
            view_count          INTEGER       DEFAULT 0,
            upvote_count        INTEGER       DEFAULT 0,
            bookmark_count      INTEGER       DEFAULT 0,
            message_count       INTEGER       DEFAULT 0,
            signal_score        INTEGER       DEFAULT 0,
            last_update_post    TIMESTAMP,
            created_at          TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── STARTUP CONTENT ───────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_startup_content (
            id                      SERIAL PRIMARY KEY,
            startup_id              INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE UNIQUE,
            about_problem           TEXT,
            about_solution          TEXT,
            about_why_now           TEXT,
            about_business_model    TEXT,
            traction_summary        TEXT,
            tech_stack              TEXT[]   DEFAULT '{}',
            video_url               VARCHAR(500),
            documentation_url       VARCHAR(500),
            roadmap_now             TEXT,
            roadmap_next            TEXT,
            roadmap_later           TEXT,
            competitors             TEXT[]   DEFAULT '{}',
            created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── METRICS ───────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_metrics (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            label       VARCHAR(80)  NOT NULL,
            value       VARCHAR(80)  NOT NULL,
            confidence  VARCHAR(20)  DEFAULT 'claimed'
                            CHECK (confidence IN ('claimed','verified','audited')),
            recorded_at DATE         DEFAULT CURRENT_DATE,
            is_current  BOOLEAN      DEFAULT TRUE,
            created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── ASKS ──────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_asks (
            id              SERIAL PRIMARY KEY,
            startup_id      INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            type            VARCHAR(20)  NOT NULL
                                CHECK (type IN ('funding','hiring','partners','customers','press','advice')),
            description     VARCHAR(600),
            urgency         VARCHAR(20)  DEFAULT 'ongoing'
                                CHECK (urgency IN ('ongoing','this-month','urgent')),
            is_active       BOOLEAN      DEFAULT TRUE,
            response_count  INTEGER      DEFAULT 0,
            created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── TEAM MEMBERS ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_team (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            name        VARCHAR(150)  NOT NULL,
            role        VARCHAR(100),
            bio         VARCHAR(400),
            avatar_url  VARCHAR(500),
            linkedin    VARCHAR(300),
            twitter     VARCHAR(100),
            sort_order  INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── UPDATES / CHANGELOG ───────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_updates (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            title       VARCHAR(300)  NOT NULL,
            content     TEXT          NOT NULL,
            type        VARCHAR(20)   DEFAULT 'other'
                            CHECK (type IN ('launch','traction','team','product','fundraising','press','pivot','other')),
            is_pinned   BOOLEAN       DEFAULT FALSE,
            created_at  TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── EDIT HISTORY ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_history (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            field_name  VARCHAR(80),
            old_value   TEXT,
            new_value   TEXT,
            changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── MESSAGES ──────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_messages (
            id              SERIAL PRIMARY KEY,
            startup_id      INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            sender_user_id  INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            sender_name     VARCHAR(150),
            sender_email    VARCHAR(255),
            subject         VARCHAR(300),
            content         TEXT    NOT NULL,
            is_read         BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # ── UPVOTES ───────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_upvotes (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id)    ON DELETE CASCADE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (startup_id, user_id)
        )
        """,

        # ── BOOKMARKS ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_bookmarks (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id)    ON DELETE CASCADE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (startup_id, user_id)
        )
        """,

        # ── FOLLOWS (startups) ────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_follows (
            id          SERIAL PRIMARY KEY,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES startuphive_users(id)    ON DELETE CASCADE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (startup_id, user_id)
        )
        """,

        # ── ACTIVITY FEED ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS startuphive_activity (
            id          SERIAL PRIMARY KEY,
            type        VARCHAR(40)  NOT NULL,
            user_id     INTEGER REFERENCES startuphive_users(id)    ON DELETE SET NULL,
            startup_id  INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            meta        JSONB        DEFAULT '{}',
            created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]

    for stmt in ddl:
        cur.execute(stmt)

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_sh_s_slug        ON startuphive_startups(slug)",
        "CREATE INDEX IF NOT EXISTS idx_sh_s_user        ON startuphive_startups(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_sh_s_active      ON startuphive_startups(is_active, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_s_upvotes     ON startuphive_startups(upvote_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_s_signal      ON startuphive_startups(signal_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_s_featured    ON startuphive_startups(is_featured)",
        "CREATE INDEX IF NOT EXISTS idx_sh_uv_startup    ON startuphive_upvotes(startup_id)",
        "CREATE INDEX IF NOT EXISTS idx_sh_uv_user       ON startuphive_upvotes(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_sh_bk_user       ON startuphive_bookmarks(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_sh_msg_startup   ON startuphive_messages(startup_id, is_read)",
        "CREATE INDEX IF NOT EXISTS idx_sh_upd_startup   ON startuphive_updates(startup_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_hist_startup  ON startuphive_history(startup_id, changed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_act_ts        ON startuphive_activity(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sh_metrics_cur   ON startuphive_metrics(startup_id, is_current)",
        "CREATE INDEX IF NOT EXISTS idx_sh_asks_startup  ON startuphive_asks(startup_id, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_sh_team_startup  ON startuphive_team(startup_id, sort_order)",
    ]

    for idx in indexes:
        cur.execute(idx)

    db.commit()
    cur.close()
    print("✅  startuphive_ schema ready — 13 tables, 16 indexes")


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def make_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXP_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:140]


def sj(val):
    """Safe JSON coerce — returns dict/list, never explodes."""
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {} if val is None else val


def sa(val):
    """Safe array coerce."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def log_activity(atype: str, user_id=None, startup_id=None, meta=None):
    try:
        db  = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO startuphive_activity (type, user_id, startup_id, meta) VALUES (%s,%s,%s,%s)",
            (atype, user_id, startup_id, json.dumps(meta or {})),
        )
        db.commit()
        cur.close()
    except Exception:
        pass


def record_history(startup_id, user_id, field, old_val, new_val):
    try:
        db  = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO startuphive_history
               (startup_id, user_id, field_name, old_value, new_value)
               VALUES (%s,%s,%s,%s,%s)""",
            (startup_id, user_id, field, str(old_val or ""), str(new_val or "")),
        )
        db.commit()
        cur.close()
    except Exception:
        pass


def fmt_startup(row, upvoted=False, bookmarked=False, following=False):
    """Convert a DB row dict to a clean API response dict."""
    return {
        "id":                 row["id"],
        "name":               row["name"],
        "slug":               row["slug"],
        "tagline":            row.get("tagline") or "",
        "logo_url":           row.get("logo_url") or "",
        "cover_url":          row.get("cover_url") or "",
        "status":             row.get("status") or "unregistered",
        "verification_level": row.get("verification_level") or "unregistered",
        "stage":              row.get("stage") or "idea",
        "categories":         sa(row.get("categories")),
        "location_based":     row.get("location_based") or "",
        "location_reach":     sa(row.get("location_reach")) or ["Global"],
        "founded_date":       row.get("founded_date") or "",
        "team_size":          row.get("team_size") or 1,
        "demo_url":           row.get("demo_url") or "",
        "contact_methods":    sj(row.get("contact_methods")),
        "is_active":          row.get("is_active", True),
        "is_featured":        row.get("is_featured", False),
        "view_count":         row.get("view_count") or 0,
        "upvote_count":       row.get("upvote_count") or 0,
        "bookmark_count":     row.get("bookmark_count") or 0,
        "message_count":      row.get("message_count") or 0,
        "signal_score":       row.get("signal_score") or 0,
        "owner_id":           row.get("user_id"),
        "owner_name":         row.get("owner_name") or "",
        "owner_username":     row.get("owner_username") or "",
        "owner_avatar":       row.get("owner_avatar") or "",
        "upvoted":            upvoted,
        "bookmarked":         bookmarked,
        "following":          following,
        "last_update_post":   row["last_update_post"].isoformat() if row.get("last_update_post") else None,
        "created_at":         row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at":         row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def fmt_user(row):
    return {
        "id":          row["id"],
        "name":        row["name"],
        "username":    row["username"],
        "email":       row.get("email") or "",
        "avatar_url":  row.get("avatar_url") or "",
        "bio":         row.get("bio") or "",
        "headline":    row.get("headline") or "",
        "website":     row.get("website") or "",
        "twitter":     row.get("twitter") or "",
        "linkedin":    row.get("linkedin") or "",
        "github":      row.get("github") or "",
        "is_verified": row.get("is_verified", False),
        "reputation":  row.get("reputation") or 0,
        "created_at":  row["created_at"].isoformat() if row.get("created_at") else None,
    }


# ──────────────────────────────────────────────────────────────
#  AUTH DECORATORS
# ──────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Token required"}), 401
        try:
            data  = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            g.uid = data["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return wrapper


def optional_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.uid = None
        auth  = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                data  = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
                g.uid = data["user_id"]
            except Exception:
                pass
        return f(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────────────────────
#  AUTH ENDPOINTS
# ──────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    d        = request.get_json() or {}
    name     = d.get("name", "").strip()
    email    = d.get("email", "").lower().strip()
    password = d.get("password", "")
    username = d.get("username", "").lower().strip()

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    # Auto-generate username if not supplied
    if not username:
        username = re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", name.lower()))[:28] or "user"

    if not re.match(r"^[a-z0-9_]{2,40}$", username):
        return jsonify({"error": "Username: 2-40 chars, lowercase letters/numbers/underscores"}), 400

    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM startuphive_users WHERE email=%s OR username=%s",
        (email, username),
    )
    if cur.fetchone():
        cur.close()
        return jsonify({"error": "Email or username already taken"}), 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    cur.execute(
        "INSERT INTO startuphive_users (name, username, email, password_hash) VALUES (%s,%s,%s,%s) RETURNING id",
        (name, username, email, pw_hash),
    )
    uid = cur.fetchone()["id"]
    db.commit()
    cur.close()
    log_activity("user_joined", uid)
    return jsonify({"token": make_token(uid), "user": {"id": uid, "name": name, "username": username, "email": email, "avatar_url": ""}}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    d          = request.get_json() or {}
    identifier = d.get("identifier", "").lower().strip()
    password   = d.get("password", "")

    if not identifier or not password:
        return jsonify({"error": "Email/username and password required"}), 400

    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT id, name, username, email, password_hash, avatar_url, bio, headline,
                  website, twitter, linkedin, github, is_verified, reputation, created_at
           FROM startuphive_users
           WHERE email=%s OR username=%s""",
        (identifier, identifier),
    )
    u = cur.fetchone()
    cur.close()

    if not u or not bcrypt.checkpw(password.encode(), u["password_hash"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    c = get_db().cursor()
    c.execute("UPDATE startuphive_users SET last_active=NOW() WHERE id=%s", (u["id"],))
    get_db().commit()
    c.close()

    return jsonify({"token": make_token(u["id"]), "user": fmt_user(u)})


@app.route("/api/auth/me", methods=["GET"])
@token_required
def get_me():
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT id, name, username, email, avatar_url, bio, headline,
                  website, twitter, linkedin, github, is_verified, reputation, created_at
           FROM startuphive_users WHERE id=%s""",
        (g.uid,),
    )
    u = cur.fetchone()
    if not u:
        cur.close()
        return jsonify({"error": "User not found"}), 404

    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE user_id=%s AND is_active=TRUE", (g.uid,))
    sc = cur.fetchone()["c"]
    cur.close()

    res = fmt_user(u)
    res["startup_count"] = sc
    return jsonify(res)


@app.route("/api/auth/profile", methods=["PUT"])
@token_required
def update_profile():
    d       = request.get_json() or {}
    allowed = ["name", "bio", "headline", "avatar_url", "website", "twitter", "linkedin", "github"]
    updates = {k: v for k, v in d.items() if k in allowed and v is not None}

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    db  = get_db()
    cur = db.cursor()
    sets  = ", ".join(f"{k}=%s" for k in updates)
    vals  = list(updates.values()) + [g.uid]
    cur.execute(f"UPDATE startuphive_users SET {sets}, updated_at=NOW() WHERE id=%s", vals)
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  FILE UPLOAD (Cloudinary)
# ──────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
@token_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f    = request.files["file"]
    kind = request.form.get("kind", "logo")
    folders = {
        "logo":   "startuphive/logos",
        "cover":  "startuphive/covers",
        "avatar": "startuphive/avatars",
        "media":  "startuphive/media",
    }
    folder = folders.get(kind, "startuphive/misc")

    try:
        result = cloudinary.uploader.upload(
            f,
            folder=folder,
            transformation=[{"width": 800, "crop": "limit", "quality": "auto:good", "fetch_format": "auto"}],
        )
        return jsonify({"url": result["secure_url"], "public_id": result["public_id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────
#  STARTUPS — LIST / SEARCH
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups", methods=["GET"])
@optional_token
def list_startups():
    page     = max(1, request.args.get("page", 1, type=int))
    per_page = min(40, max(8, request.args.get("per_page", 20, type=int)))
    sort     = request.args.get("sort", "recent")
    q        = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    stage    = request.args.get("stage", "")
    need     = request.args.get("need", "")
    featured = request.args.get("featured", "")

    conditions = ["s.is_active = TRUE"]
    params     = []

    if q:
        conditions.append("(s.name ILIKE %s OR s.tagline ILIKE %s OR %s = ANY(s.categories))")
        lq = f"%{q}%"
        params += [lq, lq, q]
    if category:
        conditions.append("%s = ANY(s.categories)")
        params.append(category)
    if stage:
        conditions.append("s.stage = %s")
        params.append(stage)
    if featured:
        conditions.append("s.is_featured = TRUE")

    # "need" filter joins to asks table
    need_join = ""
    if need:
        need_join = "JOIN startuphive_asks a ON a.startup_id = s.id AND a.is_active = TRUE AND a.type = %s"
        params.insert(0, need)

    where  = "WHERE " + " AND ".join(conditions)
    order  = {
        "recent":   "s.created_at DESC",
        "trending": "s.upvote_count DESC, s.signal_score DESC, s.created_at DESC",
        "active":   "s.updated_at DESC",
        "views":    "s.view_count DESC",
    }.get(sort, "s.created_at DESC")

    offset = (page - 1) * per_page
    db     = get_db()
    cur    = db.cursor()

    cur.execute(
        f"""SELECT s.*, u.name AS owner_name, u.username AS owner_username, u.avatar_url AS owner_avatar
            FROM startuphive_startups s
            {need_join}
            LEFT JOIN startuphive_users u ON s.user_id = u.id
            {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s""",
        (params if not need else [need] + params[1:]) + [per_page, offset]
        if need else params + [per_page, offset],
    )
    rows = cur.fetchall()

    cur.execute(
        f"""SELECT COUNT(*) AS t FROM startuphive_startups s {need_join} {where}""",
        ([need] + params[1:]) if need else params,
    )
    total = cur.fetchone()["t"]

    uv_set = bk_set = set()
    if g.uid and rows:
        ids = [r["id"] for r in rows]
        cur.execute("SELECT startup_id FROM startuphive_upvotes   WHERE user_id=%s AND startup_id=ANY(%s)", (g.uid, ids))
        uv_set = {r["startup_id"] for r in cur.fetchall()}
        cur.execute("SELECT startup_id FROM startuphive_bookmarks WHERE user_id=%s AND startup_id=ANY(%s)", (g.uid, ids))
        bk_set = {r["startup_id"] for r in cur.fetchall()}

    cur.close()
    return jsonify({
        "startups": [fmt_startup(r, r["id"] in uv_set, r["id"] in bk_set) for r in rows],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, -(-total // per_page)),
    })


# ──────────────────────────────────────────────────────────────
#  STARTUPS — MARQUEE (latest 50, for ticker strip)
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/marquee", methods=["GET"])
def marquee():
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT id, name, slug, verification_level
           FROM startuphive_startups
           WHERE is_active = TRUE
           ORDER BY updated_at DESC
           LIMIT 50"""
    )
    rows = cur.fetchall()
    cur.close()
    return jsonify([{"id": r["id"], "name": r["name"], "slug": r["slug"], "level": r["verification_level"]} for r in rows])


# ──────────────────────────────────────────────────────────────
#  STARTUPS — GET SINGLE
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<slug>", methods=["GET"])
@optional_token
def get_startup(slug):
    db  = get_db()
    cur = db.cursor()

    cur.execute(
        """SELECT s.*, u.name AS owner_name, u.username AS owner_username,
                  u.avatar_url AS owner_avatar, u.bio AS owner_bio,
                  u.headline AS owner_headline, u.twitter AS owner_twitter,
                  u.linkedin AS owner_linkedin, u.website AS owner_website
           FROM startuphive_startups s
           LEFT JOIN startuphive_users u ON s.user_id = u.id
           WHERE s.slug = %s""",
        (slug,),
    )
    s = cur.fetchone()
    if not s:
        cur.close()
        return jsonify({"error": "Startup not found"}), 404

    # Increment view count
    cur.execute("UPDATE startuphive_startups SET view_count = view_count + 1 WHERE id = %s", (s["id"],))
    get_db().commit()

    uv = bk = fw = False
    if g.uid:
        cur.execute("SELECT 1 FROM startuphive_upvotes   WHERE startup_id=%s AND user_id=%s", (s["id"], g.uid))
        uv = bool(cur.fetchone())
        cur.execute("SELECT 1 FROM startuphive_bookmarks WHERE startup_id=%s AND user_id=%s", (s["id"], g.uid))
        bk = bool(cur.fetchone())
        cur.execute("SELECT 1 FROM startuphive_follows   WHERE startup_id=%s AND user_id=%s", (s["id"], g.uid))
        fw = bool(cur.fetchone())

    # Rich data
    cur.execute("SELECT * FROM startuphive_startup_content WHERE startup_id=%s", (s["id"],))
    content = cur.fetchone()

    cur.execute("SELECT * FROM startuphive_metrics WHERE startup_id=%s AND is_current=TRUE ORDER BY recorded_at DESC", (s["id"],))
    metrics = cur.fetchall()

    cur.execute("SELECT * FROM startuphive_asks WHERE startup_id=%s AND is_active=TRUE ORDER BY urgency DESC, created_at", (s["id"],))
    asks = cur.fetchall()

    cur.execute("SELECT * FROM startuphive_team WHERE startup_id=%s ORDER BY sort_order, id", (s["id"],))
    team = cur.fetchall()

    cur.execute("SELECT * FROM startuphive_updates WHERE startup_id=%s ORDER BY is_pinned DESC, created_at DESC LIMIT 20", (s["id"],))
    updates = cur.fetchall()

    cur.execute("SELECT * FROM startuphive_history WHERE startup_id=%s ORDER BY changed_at DESC LIMIT 2", (s["id"],))
    history = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS c FROM startuphive_follows WHERE startup_id=%s", (s["id"],))
    follower_count = cur.fetchone()["c"]

    cur.close()

    result = fmt_startup(s, uv, bk, fw)
    result["owner_bio"]      = s.get("owner_bio") or ""
    result["owner_headline"] = s.get("owner_headline") or ""
    result["owner_twitter"]  = s.get("owner_twitter") or ""
    result["owner_linkedin"] = s.get("owner_linkedin") or ""
    result["owner_website"]  = s.get("owner_website") or ""
    result["follower_count"] = follower_count

    if content:
        result["content"] = {
            "about_problem":        content.get("about_problem") or "",
            "about_solution":       content.get("about_solution") or "",
            "about_why_now":        content.get("about_why_now") or "",
            "about_business_model": content.get("about_business_model") or "",
            "traction_summary":     content.get("traction_summary") or "",
            "tech_stack":           sa(content.get("tech_stack")),
            "video_url":            content.get("video_url") or "",
            "documentation_url":    content.get("documentation_url") or "",
            "roadmap_now":          content.get("roadmap_now") or "",
            "roadmap_next":         content.get("roadmap_next") or "",
            "roadmap_later":        content.get("roadmap_later") or "",
            "competitors":          sa(content.get("competitors")),
        }
    else:
        result["content"] = {}

    result["metrics"] = [
        {"id": m["id"], "label": m["label"], "value": m["value"],
         "confidence": m["confidence"], "recorded_at": str(m["recorded_at"])}
        for m in metrics
    ]
    result["asks"] = [
        {"id": a["id"], "type": a["type"], "description": a.get("description") or "",
         "urgency": a["urgency"], "response_count": a["response_count"]}
        for a in asks
    ]
    result["team"] = [
        {"id": t["id"], "name": t["name"], "role": t.get("role") or "",
         "bio": t.get("bio") or "", "avatar_url": t.get("avatar_url") or "",
         "linkedin": t.get("linkedin") or "", "twitter": t.get("twitter") or ""}
        for t in team
    ]
    result["updates"] = [
        {"id": u["id"], "title": u["title"], "content": u["content"],
         "type": u["type"], "is_pinned": u["is_pinned"],
         "created_at": u["created_at"].isoformat()}
        for u in updates
    ]
    result["history"] = [
        {"field": h["field_name"], "old": h.get("old_value") or "",
         "new": h.get("new_value") or "", "changed_at": h["changed_at"].isoformat()}
        for h in history
    ]
    return jsonify(result)


# ──────────────────────────────────────────────────────────────
#  STARTUPS — CREATE
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups", methods=["POST"])
@token_required
def create_startup():
    d    = request.get_json() or {}
    name = d.get("name", "").strip()

    if not name:
        return jsonify({"error": "Startup name is required"}), 400

    db  = get_db()
    cur = db.cursor()

    # Unique slug
    base  = slugify(name)
    slug  = base
    n     = 1
    while True:
        cur.execute("SELECT id FROM startuphive_startups WHERE slug=%s", (slug,))
        if not cur.fetchone():
            break
        slug = f"{base}-{n}"
        n   += 1

    categories = [c for c in d.get("categories", []) if c in CATEGORIES][:5]
    stage      = d.get("stage", "idea") if d.get("stage") in STAGES else "idea"
    tagline    = (d.get("tagline") or "").strip() or name

    cur.execute(
        """INSERT INTO startuphive_startups
           (user_id, name, slug, tagline, categories, stage, status, verification_level,
            location_based, location_reach, founded_date, team_size, demo_url,
            contact_methods, logo_url, cover_url)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (
            g.uid, name, slug, tagline,
            categories, stage,
            d.get("status", "unregistered"),
            d.get("verification_level", "unregistered"),
            d.get("location_based", ""),
            json.dumps(d.get("location_reach", ["Global"])),
            d.get("founded_date", ""),
            d.get("team_size", 1),
            d.get("demo_url", ""),
            json.dumps(d.get("contact_methods", {})),
            d.get("logo_url", ""),
            d.get("cover_url", ""),
        ),
    )
    sid = cur.fetchone()["id"]

    # Create startup_content row
    c = d.get("content", {})
    cur.execute(
        """INSERT INTO startuphive_startup_content
           (startup_id, about_problem, about_solution, about_why_now,
            about_business_model, traction_summary, tech_stack, video_url,
            documentation_url, roadmap_now, roadmap_next, roadmap_later)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            sid,
            c.get("about_problem", ""), c.get("about_solution", ""),
            c.get("about_why_now", ""), c.get("about_business_model", ""),
            c.get("traction_summary", ""), c.get("tech_stack", []),
            c.get("video_url", ""), c.get("documentation_url", ""),
            c.get("roadmap_now", ""), c.get("roadmap_next", ""), c.get("roadmap_later", ""),
        ),
    )
    db.commit()
    cur.close()
    log_activity("startup_listed", g.uid, sid, {"name": name})
    return jsonify({"success": True, "id": sid, "slug": slug}), 201


# ──────────────────────────────────────────────────────────────
#  STARTUPS — UPDATE
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>", methods=["PUT"])
@token_required
def update_startup(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    d       = request.get_json() or {}
    allowed = [
        "name", "tagline", "categories", "stage", "status", "verification_level",
        "location_based", "location_reach", "founded_date", "team_size",
        "demo_url", "contact_methods", "logo_url", "cover_url", "is_active",
    ]
    updates = {}
    for k in allowed:
        if k in d:
            val = d[k]
            if k in ("contact_methods", "location_reach") and isinstance(val, (dict, list)):
                val = json.dumps(val)
            updates[k] = val

    if updates:
        # Track history for key fields
        for field in ["stage", "status", "team_size"]:
            if field in updates:
                cur.execute(f"SELECT {field} FROM startuphive_startups WHERE id=%s", (sid,))
                old_row = cur.fetchone()
                if old_row:
                    record_history(sid, g.uid, field, old_row[field], updates[field])

        sets = ", ".join(f"{k}=%s" for k in updates)
        vals = list(updates.values()) + [sid]
        cur.execute(f"UPDATE startuphive_startups SET {sets}, updated_at=NOW() WHERE id=%s", vals)

    # Content update
    c = d.get("content")
    if c:
        content_allowed = [
            "about_problem", "about_solution", "about_why_now", "about_business_model",
            "traction_summary", "tech_stack", "video_url", "documentation_url",
            "roadmap_now", "roadmap_next", "roadmap_later", "competitors",
        ]
        cu = {k: v for k, v in c.items() if k in content_allowed}
        if cu:
            cur.execute("SELECT id FROM startuphive_startup_content WHERE startup_id=%s", (sid,))
            if cur.fetchone():
                s2 = ", ".join(f"{k}=%s" for k in cu)
                cur.execute(f"UPDATE startuphive_startup_content SET {s2}, updated_at=NOW() WHERE startup_id=%s",
                            list(cu.values()) + [sid])
            else:
                cur.execute(
                    "INSERT INTO startuphive_startup_content (startup_id) VALUES (%s)",
                    (sid,)
                )
                s2 = ", ".join(f"{k}=%s" for k in cu)
                cur.execute(f"UPDATE startuphive_startup_content SET {s2}, updated_at=NOW() WHERE startup_id=%s",
                            list(cu.values()) + [sid])

    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  STARTUPS — DELETE (soft)
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>", methods=["DELETE"])
@token_required
def delete_startup(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403
    cur.execute("UPDATE startuphive_startups SET is_active=FALSE WHERE id=%s", (sid,))
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  UPVOTES
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/upvote", methods=["POST"])
@token_required
def upvote(sid):
    db  = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_upvotes (startup_id, user_id) VALUES (%s,%s)", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET upvote_count=upvote_count+1, signal_score=signal_score+2 WHERE id=%s", (sid,))
        cur.execute(
            "UPDATE startuphive_users SET reputation=reputation+1 WHERE id=(SELECT user_id FROM startuphive_startups WHERE id=%s)",
            (sid,),
        )
        db.commit()
        cur.close()
        log_activity("upvote", g.uid, sid)
        return jsonify({"upvoted": True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_upvotes WHERE startup_id=%s AND user_id=%s", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET upvote_count=GREATEST(0,upvote_count-1), signal_score=GREATEST(0,signal_score-2) WHERE id=%s", (sid,))
        cur.execute(
            "UPDATE startuphive_users SET reputation=GREATEST(0,reputation-1) WHERE id=(SELECT user_id FROM startuphive_startups WHERE id=%s)",
            (sid,),
        )
        db.commit()
        cur.close()
        return jsonify({"upvoted": False})


# ──────────────────────────────────────────────────────────────
#  BOOKMARKS
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/bookmark", methods=["POST"])
@token_required
def bookmark(sid):
    db  = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_bookmarks (startup_id, user_id) VALUES (%s,%s)", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET bookmark_count=bookmark_count+1 WHERE id=%s", (sid,))
        db.commit()
        cur.close()
        return jsonify({"bookmarked": True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_bookmarks WHERE startup_id=%s AND user_id=%s", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET bookmark_count=GREATEST(0,bookmark_count-1) WHERE id=%s", (sid,))
        db.commit()
        cur.close()
        return jsonify({"bookmarked": False})


@app.route("/api/me/bookmarks", methods=["GET"])
@token_required
def my_bookmarks():
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT s.*, u.name AS owner_name, u.username AS owner_username, u.avatar_url AS owner_avatar
           FROM startuphive_startups s
           JOIN startuphive_bookmarks b ON b.startup_id=s.id
           LEFT JOIN startuphive_users u ON s.user_id=u.id
           WHERE b.user_id=%s ORDER BY b.created_at DESC""",
        (g.uid,),
    )
    rows = cur.fetchall()
    cur.close()
    return jsonify([fmt_startup(r, bookmarked=True) for r in rows])


# ──────────────────────────────────────────────────────────────
#  FOLLOWS (startup follow)
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/follow", methods=["POST"])
@token_required
def follow_startup(sid):
    db  = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_follows (startup_id, user_id) VALUES (%s,%s)", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET signal_score=signal_score+1 WHERE id=%s", (sid,))
        db.commit()
        cur.close()
        return jsonify({"following": True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_follows WHERE startup_id=%s AND user_id=%s", (sid, g.uid))
        cur.execute("UPDATE startuphive_startups SET signal_score=GREATEST(0,signal_score-1) WHERE id=%s", (sid,))
        db.commit()
        cur.close()
        return jsonify({"following": False})


# ──────────────────────────────────────────────────────────────
#  MESSAGING (contact startup)
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/message", methods=["POST"])
def send_message(sid):
    d       = request.get_json() or {}
    content = d.get("content", "").strip()
    if not content:
        return jsonify({"error": "Message content required"}), 400

    # Resolve sender
    uid = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            data = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid  = data["user_id"]
        except Exception:
            pass

    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM startuphive_startups WHERE id=%s AND is_active=TRUE", (sid,))
    if not cur.fetchone():
        cur.close()
        return jsonify({"error": "Startup not found"}), 404

    s_name = d.get("name", "")
    s_email = d.get("email", "")

    if uid:
        cur.execute("SELECT name, email FROM startuphive_users WHERE id=%s", (uid,))
        u = cur.fetchone()
        if u:
            s_name  = u["name"]
            s_email = u["email"]

    if not uid and (not s_name or not s_email):
        cur.close()
        return jsonify({"error": "Name and email required for guest messages"}), 400

    cur.execute(
        """INSERT INTO startuphive_messages
           (startup_id, sender_user_id, sender_name, sender_email, subject, content)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (sid, uid, s_name, s_email, d.get("subject", ""), content),
    )
    cur.execute("UPDATE startuphive_startups SET message_count=message_count+1, signal_score=signal_score+1 WHERE id=%s", (sid,))
    db.commit()
    cur.close()
    return jsonify({"success": True, "message": "Message delivered"}), 201


@app.route("/api/startups/<int:sid>/messages", methods=["GET"])
@token_required
def get_messages(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Not found"}), 404
    if row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute(
        """SELECT m.*, u.avatar_url AS sender_avatar
           FROM startuphive_messages m
           LEFT JOIN startuphive_users u ON m.sender_user_id=u.id
           WHERE m.startup_id=%s ORDER BY m.created_at DESC""",
        (sid,),
    )
    rows = cur.fetchall()
    cur.execute("UPDATE startuphive_messages SET is_read=TRUE WHERE startup_id=%s AND is_read=FALSE", (sid,))
    db.commit()
    cur.close()

    return jsonify([{
        "id":      r["id"],
        "name":    r["sender_name"],
        "email":   r["sender_email"],
        "subject": r.get("subject") or "",
        "content": r["content"],
        "avatar":  r.get("sender_avatar") or "",
        "is_read": r["is_read"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows])


# ──────────────────────────────────────────────────────────────
#  ASKS
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/asks", methods=["POST"])
@token_required
def add_ask(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row or row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    d       = request.get_json() or {}
    atype   = d.get("type", "")
    urgency = d.get("urgency", "ongoing")

    if atype not in ASK_TYPES:
        return jsonify({"error": "Invalid ask type"}), 400

    cur.execute(
        "INSERT INTO startuphive_asks (startup_id, type, description, urgency) VALUES (%s,%s,%s,%s) RETURNING id",
        (sid, atype, d.get("description", ""), urgency if urgency in ASK_URGENCY else "ongoing"),
    )
    aid = cur.fetchone()["id"]
    db.commit()
    cur.close()
    return jsonify({"id": aid}), 201


@app.route("/api/asks/<int:aid>/respond", methods=["POST"])
@token_required
def respond_to_ask(aid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("UPDATE startuphive_asks SET response_count=response_count+1 WHERE id=%s", (aid,))
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  METRICS
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/metrics", methods=["POST"])
@token_required
def add_metric(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row or row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    d = request.get_json() or {}
    cur.execute(
        "INSERT INTO startuphive_metrics (startup_id, label, value, confidence) VALUES (%s,%s,%s,%s) RETURNING id",
        (sid, d.get("label", ""), d.get("value", ""), d.get("confidence", "claimed")),
    )
    mid = cur.fetchone()["id"]
    db.commit()
    cur.close()
    return jsonify({"id": mid}), 201


@app.route("/api/metrics/<int:mid>", methods=["DELETE"])
@token_required
def delete_metric(mid):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """DELETE FROM startuphive_metrics m
           USING startuphive_startups s
           WHERE m.id=%s AND m.startup_id=s.id AND s.user_id=%s""",
        (mid, g.uid),
    )
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  TEAM
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/team", methods=["POST"])
@token_required
def add_team_member(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row or row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    d = request.get_json() or {}
    cur.execute(
        """INSERT INTO startuphive_team (startup_id, name, role, bio, avatar_url, linkedin, twitter)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (sid, d.get("name", ""), d.get("role", ""), d.get("bio", ""),
         d.get("avatar_url", ""), d.get("linkedin", ""), d.get("twitter", "")),
    )
    tid = cur.fetchone()["id"]
    db.commit()
    cur.close()
    return jsonify({"id": tid}), 201


@app.route("/api/team/<int:tid>", methods=["DELETE"])
@token_required
def delete_team_member(tid):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """DELETE FROM startuphive_team t
           USING startuphive_startups s
           WHERE t.id=%s AND t.startup_id=s.id AND s.user_id=%s""",
        (tid, g.uid),
    )
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  UPDATES / CHANGELOG
# ──────────────────────────────────────────────────────────────

@app.route("/api/startups/<int:sid>/updates", methods=["POST"])
@token_required
def post_update(sid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s", (sid,))
    row = cur.fetchone()
    if not row or row["user_id"] != g.uid:
        cur.close()
        return jsonify({"error": "Forbidden"}), 403

    d       = request.get_json() or {}
    title   = d.get("title", "").strip()
    content = d.get("content", "").strip()
    if not title or not content:
        return jsonify({"error": "Title and content required"}), 400

    utype = d.get("type", "other") if d.get("type") in UPDATE_TYPES else "other"

    cur.execute(
        """INSERT INTO startuphive_updates (startup_id, user_id, title, content, type, is_pinned)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (sid, g.uid, title, content, utype, d.get("is_pinned", False)),
    )
    uid = cur.fetchone()["id"]
    cur.execute(
        "UPDATE startuphive_startups SET last_update_post=NOW(), signal_score=signal_score+3, updated_at=NOW() WHERE id=%s",
        (sid,),
    )
    db.commit()
    cur.close()
    log_activity("startup_update", g.uid, sid, {"title": title, "type": utype})
    return jsonify({"id": uid}), 201


@app.route("/api/updates/<int:uid>", methods=["DELETE"])
@token_required
def delete_update(uid):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """DELETE FROM startuphive_updates u
           USING startuphive_startups s
           WHERE u.id=%s AND u.startup_id=s.id AND s.user_id=%s""",
        (uid, g.uid),
    )
    db.commit()
    cur.close()
    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────
#  DASHBOARD
# ──────────────────────────────────────────────────────────────

@app.route("/api/dashboard", methods=["GET"])
@token_required
def dashboard():
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT id, name, slug, logo_url, stage, status, is_active, is_featured,
                  view_count, upvote_count, bookmark_count, message_count, signal_score,
                  verification_level, created_at, last_update_post
           FROM startuphive_startups
           WHERE user_id=%s ORDER BY created_at DESC""",
        (g.uid,),
    )
    startups = cur.fetchall()

    ids    = [s["id"] for s in startups]
    unread = 0
    if ids:
        cur.execute(
            "SELECT COUNT(*) AS c FROM startuphive_messages WHERE startup_id=ANY(%s) AND is_read=FALSE",
            (ids,),
        )
        unread = cur.fetchone()["c"]

    cur.close()
    totals = {
        "startup_count": len(startups),
        "total_views":    sum(s["view_count"]    for s in startups),
        "total_upvotes":  sum(s["upvote_count"]  for s in startups),
        "total_bookmarks":sum(s["bookmark_count"] for s in startups),
        "total_messages": sum(s["message_count"] for s in startups),
        "unread_messages": unread,
    }
    return jsonify({
        "startups": [{
            "id":                 s["id"],
            "name":               s["name"],
            "slug":               s["slug"],
            "logo_url":           s.get("logo_url") or "",
            "stage":              s["stage"],
            "status":             s["status"],
            "is_active":          s["is_active"],
            "is_featured":        s["is_featured"],
            "view_count":         s["view_count"],
            "upvote_count":       s["upvote_count"],
            "bookmark_count":     s["bookmark_count"],
            "message_count":      s["message_count"],
            "signal_score":       s["signal_score"],
            "verification_level": s["verification_level"],
            "last_update_post":   s["last_update_post"].isoformat() if s["last_update_post"] else None,
            "created_at":         s["created_at"].isoformat(),
        } for s in startups],
        "totals": totals,
    })


# ──────────────────────────────────────────────────────────────
#  PUBLIC USER PROFILE
# ──────────────────────────────────────────────────────────────

@app.route("/api/users/<username>", methods=["GET"])
def get_user(username):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT id, name, username, avatar_url, bio, headline,
                  website, twitter, linkedin, github, is_verified, reputation, created_at
           FROM startuphive_users WHERE username=%s""",
        (username,),
    )
    u = cur.fetchone()
    if not u:
        cur.close()
        return jsonify({"error": "User not found"}), 404

    cur.execute(
        """SELECT id, name, slug, tagline, logo_url, categories, stage, status,
                  upvote_count, view_count, is_active, created_at
           FROM startuphive_startups
           WHERE user_id=%s AND is_active=TRUE ORDER BY created_at DESC""",
        (u["id"],),
    )
    startups = cur.fetchall()
    cur.close()

    return jsonify({**fmt_user(u), "startups": [fmt_startup(s) for s in startups]})


# ──────────────────────────────────────────────────────────────
#  SEARCH
# ──────────────────────────────────────────────────────────────

@app.route("/api/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"startups": [], "users": []})

    db  = get_db()
    cur = db.cursor()
    lq  = f"%{q}%"

    cur.execute(
        """SELECT id, name, slug, tagline, logo_url, categories, stage, upvote_count
           FROM startuphive_startups
           WHERE is_active=TRUE AND (name ILIKE %s OR tagline ILIKE %s OR %s=ANY(categories))
           ORDER BY upvote_count DESC LIMIT 8""",
        (lq, lq, q),
    )
    startups = cur.fetchall()

    cur.execute(
        """SELECT id, name, username, avatar_url, headline, is_verified
           FROM startuphive_users WHERE name ILIKE %s OR username ILIKE %s LIMIT 5""",
        (lq, lq),
    )
    users = cur.fetchall()
    cur.close()

    return jsonify({
        "startups": [{"id": s["id"], "name": s["name"], "slug": s["slug"],
                      "tagline": s.get("tagline") or "", "logo_url": s.get("logo_url") or "",
                      "categories": sa(s.get("categories")), "stage": s["stage"],
                      "upvote_count": s["upvote_count"]} for s in startups],
        "users": [{"id": u["id"], "name": u["name"], "username": u["username"],
                   "avatar_url": u.get("avatar_url") or "", "headline": u.get("headline") or "",
                   "is_verified": u["is_verified"]} for u in users],
    })


# ──────────────────────────────────────────────────────────────
#  PLATFORM STATS
# ──────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def platform_stats():
    db  = get_db()
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE is_active=TRUE")
    total_startups = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_users")
    total_users = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE is_active=TRUE AND created_at >= NOW()-INTERVAL '7 days'")
    new_this_week = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_upvotes WHERE created_at >= CURRENT_DATE")
    upvotes_today = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_messages WHERE created_at >= NOW()-INTERVAL '7 days'")
    messages_week = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE status='for_sale' AND is_active=TRUE")
    for_sale = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE verification_level IN ('verified','audited') AND is_active=TRUE")
    verified = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE stage IN ('growing','scaling') AND is_active=TRUE")
    live = cur.fetchone()["c"]
    cur.close()

    return jsonify({
        "total_startups":   total_startups,
        "total_users":      total_users,
        "new_this_week":    new_this_week,
        "upvotes_today":    upvotes_today,
        "messages_week":    messages_week,
        "for_sale":         for_sale,
        "verified":         verified,
        "live_scaling":     live,
    })


# ──────────────────────────────────────────────────────────────
#  ACTIVITY FEED
# ──────────────────────────────────────────────────────────────

@app.route("/api/activity", methods=["GET"])
def activity_feed():
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT a.type, a.meta, a.created_at,
                  u.name AS user_name, u.username AS user_username, u.avatar_url AS user_avatar,
                  s.name AS startup_name, s.slug AS startup_slug, s.logo_url AS startup_logo,
                  s.categories AS startup_categories
           FROM startuphive_activity a
           LEFT JOIN startuphive_users    u ON a.user_id    = u.id
           LEFT JOIN startuphive_startups s ON a.startup_id = s.id
           WHERE a.type IN ('startup_listed','startup_update','upvote','user_joined')
           ORDER BY a.created_at DESC LIMIT 25""",
    )
    rows = cur.fetchall()
    cur.close()

    return jsonify([{
        "type":          r["type"],
        "meta":          sj(r["meta"]),
        "user_name":     r.get("user_name") or "",
        "user_username": r.get("user_username") or "",
        "user_avatar":   r.get("user_avatar") or "",
        "startup_name":  r.get("startup_name") or "",
        "startup_slug":  r.get("startup_slug") or "",
        "startup_logo":  r.get("startup_logo") or "",
        "startup_categories": sa(r.get("startup_categories")),
        "created_at":    r["created_at"].isoformat(),
    } for r in rows])


# ──────────────────────────────────────────────────────────────
#  HEALTH / PING
# ──────────────────────────────────────────────────────────────

@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive", "service": "startuphive", "ts": datetime.datetime.utcnow().isoformat()})


@app.route("/")
def root():
    return jsonify({"service": "StartupHive API", "version": "2.0.0", "status": "running"})


# ──────────────────────────────────────────────────────────────
#  BOOT
# ──────────────────────────────────────────────────────────────
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
