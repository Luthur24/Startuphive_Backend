"""
DEVMARKET — Developer Marketplace Platform
Backend: Python / Flask
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
import datetime
import uuid
import re
import json
import requests
import cloudinary
import cloudinary.uploader
from functools import wraps

# ─────────────────────────────────────────────────────────────────────────────
# CREDENTIALS  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

DB_URL             = "postgres://avnadmin:AVNS_q_zR9FvhvJHJGbiL0zp@pg-235735e2-ub7499710-7253.j.aivencloud.com:11602/defaultdb?sslmode=require"
JWT_SECRET         = "devmarket_jwt_secret_key_2024_multibillion"

CLOUDINARY_CLOUD   = "ddusfl7pi"
CLOUDINARY_KEY     = "599965682593626"
CLOUDINARY_SECRET  = "pUcb90_1jtv-rDlHXRRsfDcBK5k"

MISTRAL_API_KEY    = "uZIGi6VCzkcJ0i5X5mYYc0Nr1XWX21YR"
MISTRAL_URL        = "https://api.mistral.ai/v1/chat/completions"

TAVILY_API_KEY     = "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"
TAVILY_URL         = "https://api.tavily.com/search"

# ─────────────────────────────────────────────────────────────────────────────
# APP & CORS
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = JWT_SECRET

CORS(app)   # allow all origins globally

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

# ─────────────────────────────────────────────────────────────────────────────
# CLOUDINARY
# ─────────────────────────────────────────────────────────────────────────────

cloudinary.config(
    cloud_name = CLOUDINARY_CLOUD,
    api_key    = CLOUDINARY_KEY,
    api_secret = CLOUDINARY_SECRET,
    secure     = True,
)

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_db():
    """Open a connection with autocommit so every statement commits immediately."""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    return conn


def db_execute(sql, params=(), fetch="none"):
    """
    Thin helper:
      fetch="none"  → execute and return None
      fetch="one"   → return single RealDictRow (or None)
      fetch="all"   → return list of RealDictRow
    Raises on error so callers can handle it.
    """
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params)
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        return None
    finally:
        cur.close()
        conn.close()


def safe_dict(row):
    """Convert a RealDictRow to a plain dict, stringify UUID fields."""
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.isoformat()
    return d


def safe_list(rows):
    return [safe_dict(r) for r in rows]

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE INIT — runs at module load (works with gunicorn)
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables if they don't exist.
    Also runs ALTER TABLE … ADD COLUMN IF NOT EXISTS for every column that
    may be missing on a table created by an older schema version.
    Each statement is wrapped independently so one failure can't block the rest.
    """
    conn = get_db()
    cur  = conn.cursor()

    statements = [

        # ── users ────────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_users (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username         VARCHAR(50)  UNIQUE NOT NULL,
            email            VARCHAR(255) UNIQUE NOT NULL,
            password_hash    TEXT         NOT NULL,
            full_name        VARCHAR(120),
            bio              TEXT,
            avatar_url       TEXT,
            cover_url        TEXT,
            github_url       TEXT,
            website_url      TEXT,
            twitter_url      TEXT,
            linkedin_url     TEXT,
            skills           TEXT[],
            role             VARCHAR(20)  DEFAULT 'seller',
            is_verified      BOOLEAN      DEFAULT FALSE,
            reputation_score INTEGER      DEFAULT 0,
            total_sales      INTEGER      DEFAULT 0,
            total_purchases  INTEGER      DEFAULT 0,
            location         VARCHAR(100),
            badge            VARCHAR(50)  DEFAULT 'newcomer',
            is_online        BOOLEAN      DEFAULT FALSE,
            last_active      TIMESTAMP    DEFAULT NOW(),
            joined_at        TIMESTAMP    DEFAULT NOW()
        )""",

        # ── categories ───────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_categories (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name          VARCHAR(100) NOT NULL,
            slug          VARCHAR(100) UNIQUE NOT NULL,
            description   TEXT,
            icon          TEXT,
            color         VARCHAR(20),
            product_count INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT NOW()
        )""",

        # ── products ─────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_products (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seller_id          UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            category_id        UUID REFERENCES devmarket_categories(id),
            title              VARCHAR(255) NOT NULL,
            slug               VARCHAR(255) UNIQUE NOT NULL,
            short_description  TEXT,
            description        TEXT NOT NULL,
            price              DECIMAL(10,2) NOT NULL,
            currency           VARCHAR(10)  DEFAULT 'USD',
            product_type       VARCHAR(50)  NOT NULL,
            tags               TEXT[],
            tech_stack         TEXT[],
            images             TEXT[],
            demo_url           TEXT,
            repo_url           TEXT,
            documentation_url  TEXT,
            live_preview_url   TEXT,
            version            VARCHAR(20)  DEFAULT '1.0.0',
            license            VARCHAR(50)  DEFAULT 'MIT',
            file_size          VARCHAR(20),
            downloads          INTEGER      DEFAULT 0,
            views              INTEGER      DEFAULT 0,
            likes              INTEGER      DEFAULT 0,
            is_featured        BOOLEAN      DEFAULT FALSE,
            is_active          BOOLEAN      DEFAULT TRUE,
            is_approved        BOOLEAN      DEFAULT TRUE,
            rating_avg         DECIMAL(3,2) DEFAULT 0,
            review_count       INTEGER      DEFAULT 0,
            created_at         TIMESTAMP    DEFAULT NOW(),
            updated_at         TIMESTAMP    DEFAULT NOW()
        )""",

        # ── orders ───────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_orders (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            buyer_id          UUID REFERENCES devmarket_users(id),
            seller_id         UUID REFERENCES devmarket_users(id),
            product_id        UUID REFERENCES devmarket_products(id),
            status            VARCHAR(30)   DEFAULT 'pending_contact',
            negotiated_price  DECIMAL(10,2),
            notes             TEXT,
            buyer_confirmed   BOOLEAN DEFAULT FALSE,
            seller_confirmed  BOOLEAN DEFAULT FALSE,
            created_at        TIMESTAMP DEFAULT NOW(),
            updated_at        TIMESTAMP DEFAULT NOW()
        )""",

        # ── conversations ────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_conversations (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            participant_one    UUID REFERENCES devmarket_users(id),
            participant_two    UUID REFERENCES devmarket_users(id),
            product_id         UUID REFERENCES devmarket_products(id),
            order_id           UUID REFERENCES devmarket_orders(id),
            last_message       TEXT,
            last_message_at    TIMESTAMP DEFAULT NOW(),
            unread_count_one   INTEGER DEFAULT 0,
            unread_count_two   INTEGER DEFAULT 0,
            created_at         TIMESTAMP DEFAULT NOW()
        )""",

        # ── messages ─────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_messages (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id  UUID REFERENCES devmarket_conversations(id) ON DELETE CASCADE,
            sender_id        UUID REFERENCES devmarket_users(id),
            content          TEXT NOT NULL,
            message_type     VARCHAR(20) DEFAULT 'text',
            attachment_url   TEXT,
            is_read          BOOLEAN DEFAULT FALSE,
            is_deleted       BOOLEAN DEFAULT FALSE,
            created_at       TIMESTAMP DEFAULT NOW()
        )""",

        # ── reviews ──────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_reviews (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id   UUID REFERENCES devmarket_products(id) ON DELETE CASCADE,
            reviewer_id  UUID REFERENCES devmarket_users(id),
            rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            title        VARCHAR(255),
            content      TEXT NOT NULL,
            helpful_votes INTEGER DEFAULT 0,
            created_at   TIMESTAMP DEFAULT NOW(),
            UNIQUE(product_id, reviewer_id)
        )""",

        # ── bookmarks ────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_bookmarks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            product_id  UUID REFERENCES devmarket_products(id) ON DELETE CASCADE,
            created_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )""",

        # ── notifications ────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_notifications (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            type       VARCHAR(50)  NOT NULL,
            title      VARCHAR(255) NOT NULL,
            body       TEXT,
            link       TEXT,
            is_read    BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # ── portfolio ────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_portfolio (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            title       VARCHAR(255) NOT NULL,
            description TEXT,
            image_url   TEXT,
            project_url TEXT,
            tech_stack  TEXT[],
            created_at  TIMESTAMP DEFAULT NOW()
        )""",

        # ── articles ─────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_articles (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            author_id    UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            title        VARCHAR(500) NOT NULL,
            slug         VARCHAR(500) UNIQUE NOT NULL,
            content      TEXT NOT NULL,
            cover_image  TEXT,
            tags         TEXT[],
            views        INTEGER DEFAULT 0,
            likes        INTEGER DEFAULT 0,
            is_published BOOLEAN DEFAULT TRUE,
            created_at   TIMESTAMP DEFAULT NOW(),
            updated_at   TIMESTAMP DEFAULT NOW()
        )""",

        # ── jobs ─────────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_jobs (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            poster_id          UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            title              VARCHAR(255) NOT NULL,
            company            VARCHAR(100),
            description        TEXT NOT NULL,
            job_type           VARCHAR(50),
            location           VARCHAR(100),
            salary_range       VARCHAR(100),
            tech_stack         TEXT[],
            is_remote          BOOLEAN DEFAULT TRUE,
            is_active          BOOLEAN DEFAULT TRUE,
            applications_count INTEGER DEFAULT 0,
            created_at         TIMESTAMP DEFAULT NOW()
        )""",

        # ── ai chat sessions ─────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS devmarket_ai_chats (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID REFERENCES devmarket_users(id) ON DELETE CASCADE,
            session_id VARCHAR(100) NOT NULL,
            messages   JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",

        # ── seed categories ──────────────────────────────────────────────────
        """INSERT INTO devmarket_categories (name, slug, description, icon, color) VALUES
            ('APIs & Integrations', 'apis',         'REST, GraphQL, WebSocket APIs and third-party integrations', '🔌', '#6366f1'),
            ('UI Templates',        'ui-templates', 'React, Vue, Angular templates and component libraries',      '🎨', '#ec4899'),
            ('Developer Tools',     'dev-tools',    'CLI tools, extensions, productivity boosters',               '🔧', '#f59e0b'),
            ('Scripts & Bots',      'scripts',      'Automation scripts, bots, crawlers, and schedulers',         '🤖', '#10b981'),
            ('Datasets',            'datasets',     'Curated datasets for ML, analytics, and research',           '📊', '#3b82f6'),
            ('Plugins & Extensions','plugins',      'Browser extensions, IDE plugins, CMS plugins',               '🧩', '#8b5cf6'),
            ('Mobile SDKs',         'mobile',       'iOS, Android, React Native, Flutter kits',                   '📱', '#ef4444'),
            ('Security Tools',      'security',     'Pen-testing tools, auth libraries, encryption modules',      '🔐', '#f97316'),
            ('AI & ML Models',      'ai-ml',        'Pre-trained models, fine-tuned LLMs, ML pipelines',          '🧠', '#06b6d4'),
            ('DevOps & Infra',      'devops',       'Docker configs, Kubernetes charts, CI/CD pipelines',         '⚙️', '#84cc16'),
            ('Blockchain & Web3',   'web3',         'Smart contracts, DeFi tools, NFT utilities',                 '⛓️', '#a855f7'),
            ('Game Dev Assets',     'game-dev',     'Unity assets, Unreal plugins, game frameworks',              '🎮', '#f43f5e')
        ON CONFLICT (slug) DO NOTHING""",
    ]

    for stmt in statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"[init_db] skipped: {e}")

    cur.close()
    conn.close()
    print("✅ Devmarket DB ready")


# Run immediately so gunicorn workers initialise the schema on startup.
try:
    init_db()
except Exception as _boot_err:
    print(f"[boot] init_db failed: {_boot_err}")

# ─────────────────────────────────────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def make_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def token_required(f):
    """Decorator — 401 if no valid Bearer token."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        try:
            payload = decode_token(auth.split(" ", 1)[1])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(payload["user_id"], *args, **kwargs)
    return wrapper


def optional_auth(f):
    """Decorator — passes user_id or None; never rejects."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                uid = decode_token(auth.split(" ", 1)[1])["user_id"]
            except Exception:
                pass
        return f(uid, *args, **kwargs)
    return wrapper


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH / INIT
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    db = "error"
    try:
        db_execute("SELECT 1")
        db = "connected"
    except Exception as e:
        db = str(e)
    return jsonify({"status": "ok", "database": db, "platform": "Devmarket"})


@app.route("/api/init")
def force_init():
    """Manually re-run schema migrations. Useful after a deploy."""
    try:
        init_db()
        return jsonify({"status": "ok", "message": "Schema synced"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    d        = request.get_json() or {}
    username = d.get("username", "").strip().lower()
    email    = d.get("email",    "").strip().lower()
    password = d.get("password", "")
    fullname = d.get("full_name","").strip()

    if not all([username, email, password, fullname]):
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """INSERT INTO devmarket_users (username, email, password_hash, full_name, role)
               VALUES (%s, %s, %s, %s, 'seller')
               RETURNING id, username, email, full_name, role,
                         avatar_url, badge, reputation_score, is_verified""",
            (username, email, pw_hash, fullname),
        )
        user           = safe_dict(cur.fetchone())
        token          = make_token(user["id"])
        return jsonify({"token": token, "user": user}), 201

    except psycopg2.IntegrityError as e:
        msg = str(e)
        if "username" in msg:
            return jsonify({"error": "Username already taken"}), 409
        if "email" in msg:
            return jsonify({"error": "Email already registered"}), 409
        return jsonify({"error": "Registration failed"}), 500
    finally:
        cur.close()
        conn.close()


@app.route("/api/auth/login", methods=["POST"])
def login():
    d          = request.get_json() or {}
    identifier = d.get("identifier", "").strip().lower()
    password   = d.get("password",   "")

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM devmarket_users WHERE email=%s OR username=%s",
            (identifier, identifier),
        )
        user = cur.fetchone()

        if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return jsonify({"error": "Invalid credentials"}), 401

        # update last_active and online flag
        cur.execute(
            "UPDATE devmarket_users SET last_active=NOW(), is_online=TRUE WHERE id=%s",
            (user["id"],),
        )

        token    = make_token(str(user["id"]))
        safe_user = {
            "id":               str(user["id"]),
            "username":         user["username"],
            "email":            user["email"],
            "full_name":        user["full_name"],
            "avatar_url":       user["avatar_url"],
            "role":             user["role"],
            "badge":            user["badge"],
            "reputation_score": user["reputation_score"],
            "is_verified":      user["is_verified"],
            "total_sales":      user["total_sales"],
            "location":         user["location"],
        }
        return jsonify({"token": token, "user": safe_user})
    finally:
        cur.close()
        conn.close()


@app.route("/api/auth/me")
@token_required
def get_me(uid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT id, username, email, full_name, bio, avatar_url, cover_url,
                      github_url, website_url, twitter_url, linkedin_url, skills,
                      role, is_verified, reputation_score, total_sales, total_purchases,
                      joined_at, last_active, location, badge
               FROM devmarket_users WHERE id=%s::uuid""",
            (uid,),
        )
        user = cur.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": safe_dict(user)})
    finally:
        cur.close()
        conn.close()


@app.route("/api/auth/update-profile", methods=["PUT"])
@token_required
def update_profile(uid):
    d       = request.get_json() or {}
    allowed = ["full_name", "bio", "github_url", "website_url",
               "twitter_url", "linkedin_url", "location", "skills"]
    updates = {k: v for k, v in d.items() if k in allowed}
    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    set_clause = ", ".join(f"{k}=%s" for k in updates)
    vals       = list(updates.values()) + [uid]
    db_execute(f"UPDATE devmarket_users SET {set_clause} WHERE id=%s::uuid", vals)
    return jsonify({"message": "Profile updated"})


@app.route("/api/auth/logout", methods=["POST"])
@token_required
def logout(uid):
    db_execute("UPDATE devmarket_users SET is_online=FALSE WHERE id=%s::uuid", (uid,))
    return jsonify({"message": "Logged out"})

# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD (Cloudinary)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/upload/image", methods=["POST"])
@token_required
def upload_image(uid):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    try:
        result = cloudinary.uploader.upload(
            request.files["file"],
            folder=request.form.get("folder", "devmarket/general"),
            transformation=[{"quality": "auto", "fetch_format": "auto"}],
        )
        return jsonify({"url": result["secure_url"], "public_id": result["public_id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/avatar", methods=["POST"])
@token_required
def upload_avatar(uid):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    try:
        result = cloudinary.uploader.upload(
            request.files["file"],
            folder="devmarket/avatars",
            transformation=[
                {"width": 300, "height": 300, "crop": "fill", "gravity": "face"},
                {"quality": "auto", "fetch_format": "auto"},
            ],
        )
        db_execute(
            "UPDATE devmarket_users SET avatar_url=%s WHERE id=%s::uuid",
            (result["secure_url"], uid),
        )
        return jsonify({"url": result["secure_url"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORIES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/categories")
def get_categories():
    rows = db_execute("SELECT * FROM devmarket_categories ORDER BY name", fetch="all")
    return jsonify({"categories": safe_list(rows or [])})

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/products")
@optional_auth
def get_products(uid):
    page     = max(1, int(request.args.get("page",     1)))
    per_page = min(50, int(request.args.get("per_page", 12)))
    offset   = (page - 1) * per_page

    category     = request.args.get("category", "").strip()
    search       = request.args.get("search",   "").strip()
    sort         = request.args.get("sort",     "newest")
    product_type = request.args.get("type",     "").strip()
    min_price    = request.args.get("min_price")
    max_price    = request.args.get("max_price")

    clauses = ["p.is_active=TRUE", "p.is_approved=TRUE"]
    params  = []

    if category:
        clauses.append("c.slug=%s")
        params.append(category)
    if search:
        clauses.append("(p.title ILIKE %s OR p.short_description ILIKE %s OR %s=ANY(p.tags))")
        params += [f"%{search}%", f"%{search}%", search]
    if product_type:
        clauses.append("p.product_type=%s")
        params.append(product_type)
    if min_price:
        clauses.append("p.price>=%s")
        params.append(float(min_price))
    if max_price:
        clauses.append("p.price<=%s")
        params.append(float(max_price))

    order_map = {
        "newest":     "p.created_at DESC",
        "oldest":     "p.created_at ASC",
        "price_asc":  "p.price ASC",
        "price_desc": "p.price DESC",
        "popular":    "p.downloads DESC",
        "rating":     "p.rating_avg DESC",
        "trending":   "p.views DESC",
    }
    order_by  = order_map.get(sort, "p.created_at DESC")
    where_sql = " AND ".join(clauses)

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            f"""SELECT p.*, c.name AS category_name, c.slug AS category_slug,
                       c.icon AS category_icon,
                       u.username, u.full_name AS seller_name,
                       u.avatar_url AS seller_avatar,
                       u.is_verified AS seller_verified,
                       u.badge AS seller_badge
                FROM devmarket_products p
                LEFT JOIN devmarket_categories c ON p.category_id = c.id
                LEFT JOIN devmarket_users      u ON p.seller_id   = u.id
                WHERE {where_sql}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        products = safe_list(cur.fetchall())

        cur.execute(
            f"""SELECT COUNT(*) AS n
                FROM devmarket_products p
                LEFT JOIN devmarket_categories c ON p.category_id = c.id
                WHERE {where_sql}""",
            params,
        )
        total = int((cur.fetchone() or {}).get("n", 0))

        return jsonify({
            "products": products,
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "pages":    max(1, (total + per_page - 1) // per_page),
        })
    finally:
        cur.close()
        conn.close()


@app.route("/api/products/<pid>")
@optional_auth
def get_product(uid, pid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT p.*, c.name AS category_name, c.slug AS category_slug,
                      c.icon AS category_icon,
                      u.username, u.full_name AS seller_name,
                      u.avatar_url AS seller_avatar, u.bio AS seller_bio,
                      u.is_verified AS seller_verified,
                      u.badge AS seller_badge,
                      u.reputation_score AS seller_reputation,
                      u.total_sales AS seller_total_sales
               FROM devmarket_products p
               LEFT JOIN devmarket_categories c ON p.category_id = c.id
               LEFT JOIN devmarket_users      u ON p.seller_id   = u.id
               WHERE p.slug=%s OR p.id::text=%s""",
            (pid, pid),
        )
        product = cur.fetchone()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        product = safe_dict(product)

        # increment views
        cur.execute(
            "UPDATE devmarket_products SET views=views+1 WHERE id=%s::uuid",
            (product["id"],),
        )

        # reviews
        cur.execute(
            """SELECT r.*, u.username, u.full_name, u.avatar_url
               FROM devmarket_reviews r
               JOIN devmarket_users u ON r.reviewer_id = u.id
               WHERE r.product_id=%s::uuid
               ORDER BY r.created_at DESC LIMIT 20""",
            (product["id"],),
        )
        reviews = safe_list(cur.fetchall())

        # bookmark status
        is_bookmarked = False
        if uid:
            cur.execute(
                "SELECT 1 FROM devmarket_bookmarks WHERE user_id=%s::uuid AND product_id=%s::uuid",
                (uid, product["id"]),
            )
            is_bookmarked = cur.fetchone() is not None

        # related
        cur.execute(
            """SELECT p.id, p.title, p.slug, p.price, p.images, p.rating_avg,
                      p.downloads, p.product_type, u.username, u.avatar_url
               FROM devmarket_products p
               JOIN devmarket_users u ON p.seller_id = u.id
               WHERE p.category_id=%s::uuid AND p.id!=%s::uuid AND p.is_active=TRUE
               ORDER BY p.rating_avg DESC LIMIT 4""",
            (product["category_id"], product["id"]),
        )
        related = safe_list(cur.fetchall())

        return jsonify({
            "product":      product,
            "reviews":      reviews,
            "related":      related,
            "is_bookmarked": is_bookmarked,
        })
    finally:
        cur.close()
        conn.close()


@app.route("/api/products", methods=["POST"])
@token_required
def create_product(uid):
    d        = request.get_json() or {}
    required = ["title", "description", "price", "product_type", "category_id"]
    if not all(d.get(f) for f in required):
        return jsonify({"error": "Missing required fields"}), 400

    slug_base = slugify(d["title"])
    slug      = slug_base

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # unique slug
        n = 1
        while True:
            cur.execute("SELECT 1 FROM devmarket_products WHERE slug=%s", (slug,))
            if not cur.fetchone():
                break
            slug = f"{slug_base}-{n}"; n += 1

        cur.execute(
            """INSERT INTO devmarket_products
               (seller_id, category_id, title, slug, short_description, description,
                price, product_type, tags, tech_stack, images, demo_url, repo_url,
                documentation_url, live_preview_url, version, license, file_size)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING *""",
            (
                uid, d["category_id"], d["title"], slug,
                d.get("short_description"), d["description"],
                d["price"], d["product_type"],
                d.get("tags", []), d.get("tech_stack", []),
                d.get("images", []), d.get("demo_url"), d.get("repo_url"),
                d.get("documentation_url"), d.get("live_preview_url"),
                d.get("version", "1.0.0"), d.get("license", "MIT"),
                d.get("file_size"),
            ),
        )
        product = safe_dict(cur.fetchone())

        # update category count
        cur.execute(
            "UPDATE devmarket_categories SET product_count=product_count+1 WHERE id=%s::uuid",
            (d["category_id"],),
        )
        return jsonify({"product": product}), 201
    finally:
        cur.close()
        conn.close()


@app.route("/api/products/<pid>", methods=["PUT"])
@token_required
def update_product(uid, pid):
    d = request.get_json() or {}
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT seller_id FROM devmarket_products WHERE id=%s::uuid", (pid,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Product not found"}), 404
        if str(row["seller_id"]) != uid:
            return jsonify({"error": "Not authorised"}), 403

        allowed = ["title", "short_description", "description", "price", "tags",
                   "tech_stack", "images", "demo_url", "repo_url",
                   "documentation_url", "version", "is_active"]
        updates = {k: v for k, v in d.items() if k in allowed}
        if not updates:
            return jsonify({"error": "Nothing to update"}), 400
        updates["updated_at"] = datetime.datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        cur.execute(
            f"UPDATE devmarket_products SET {set_clause} WHERE id=%s::uuid",
            list(updates.values()) + [pid],
        )
        return jsonify({"message": "Product updated"})
    finally:
        cur.close()
        conn.close()


@app.route("/api/products/<pid>", methods=["DELETE"])
@token_required
def delete_product(uid, pid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT seller_id FROM devmarket_products WHERE id=%s::uuid", (pid,))
        row = cur.fetchone()
        if not row or str(row["seller_id"]) != uid:
            return jsonify({"error": "Not authorised"}), 403
        cur.execute("DELETE FROM devmarket_products WHERE id=%s::uuid", (pid,))
        return jsonify({"message": "Product deleted"})
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# TRENDING & FEATURED
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/trending")
def get_trending():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT p.id, p.title, p.slug, p.price, p.short_description,
                      p.images, p.rating_avg, p.review_count, p.downloads,
                      p.views, p.product_type, p.tags,
                      u.username, u.avatar_url, u.is_verified,
                      c.name AS category_name, c.icon AS category_icon
               FROM devmarket_products p
               JOIN devmarket_users      u ON p.seller_id   = u.id
               LEFT JOIN devmarket_categories c ON p.category_id = c.id
               WHERE p.is_active=TRUE
               ORDER BY (p.views + p.downloads*3 + p.likes*5) DESC
               LIMIT 12"""
        )
        return jsonify({"trending": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()


@app.route("/api/featured")
def get_featured():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # try featured flag first, fall back to top rated
        cur.execute(
            """SELECT p.id, p.title, p.slug, p.price, p.short_description,
                      p.images, p.rating_avg, p.review_count, p.downloads,
                      p.product_type, p.tags, p.tech_stack,
                      u.username, u.full_name, u.avatar_url, u.is_verified,
                      c.name AS category_name, c.icon AS category_icon,
                      c.color AS category_color
               FROM devmarket_products p
               JOIN devmarket_users      u ON p.seller_id   = u.id
               LEFT JOIN devmarket_categories c ON p.category_id = c.id
               WHERE p.is_active=TRUE
               ORDER BY p.is_featured DESC, p.rating_avg DESC, p.downloads DESC
               LIMIT 6"""
        )
        return jsonify({"featured": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH SUGGESTIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/search/suggestions")
def search_suggestions():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"suggestions": []})
    rows = db_execute(
        "SELECT title, slug, price, product_type FROM devmarket_products "
        "WHERE title ILIKE %s AND is_active=TRUE LIMIT 8",
        (f"%{q}%",),
        fetch="all",
    )
    return jsonify({"suggestions": safe_list(rows or [])})

# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM STATS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def platform_stats():
    stats = {"users": 0, "products": 0, "orders": 0, "downloads": 0}
    queries = [
        ("users",     "SELECT COUNT(*)        AS n FROM devmarket_users"),
        ("products",  "SELECT COUNT(*)        AS n FROM devmarket_products WHERE is_active=TRUE"),
        ("orders",    "SELECT COUNT(*)        AS n FROM devmarket_orders"),
        ("downloads", "SELECT COALESCE(SUM(downloads),0) AS n FROM devmarket_products"),
    ]
    for key, sql in queries:
        try:
            row = db_execute(sql, fetch="one")
            stats[key] = int(row["n"]) if row else 0
        except Exception:
            pass
    return jsonify(stats)

# ─────────────────────────────────────────────────────────────────────────────
# BOOKMARKS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/products/<pid>/bookmark", methods=["POST"])
@token_required
def toggle_bookmark(uid, pid):
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM devmarket_bookmarks WHERE user_id=%s::uuid AND product_id=%s::uuid",
            (uid, pid),
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM devmarket_bookmarks WHERE user_id=%s::uuid AND product_id=%s::uuid",
                (uid, pid),
            )
            cur.execute(
                "UPDATE devmarket_products SET likes=GREATEST(0,likes-1) WHERE id=%s::uuid", (pid,)
            )
            return jsonify({"bookmarked": False})
        else:
            cur.execute(
                "INSERT INTO devmarket_bookmarks (user_id, product_id) VALUES (%s::uuid,%s::uuid)",
                (uid, pid),
            )
            cur.execute(
                "UPDATE devmarket_products SET likes=likes+1 WHERE id=%s::uuid", (pid,)
            )
            return jsonify({"bookmarked": True})
    finally:
        cur.close()
        conn.close()


@app.route("/api/bookmarks")
@token_required
def get_bookmarks(uid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT p.id, p.title, p.slug, p.price, p.images, p.rating_avg,
                      p.downloads, p.product_type, p.short_description,
                      u.username, u.avatar_url
               FROM devmarket_bookmarks b
               JOIN devmarket_products p ON b.product_id = p.id
               JOIN devmarket_users    u ON p.seller_id   = u.id
               WHERE b.user_id=%s::uuid
               ORDER BY b.created_at DESC""",
            (uid,),
        )
        return jsonify({"bookmarks": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/products/<pid>/reviews", methods=["POST"])
@token_required
def add_review(uid, pid):
    d       = request.get_json() or {}
    rating  = d.get("rating")
    content = d.get("content", "").strip()
    title   = d.get("title",   "").strip()

    if not rating or not content:
        return jsonify({"error": "Rating and content required"}), 400
    if not 1 <= int(rating) <= 5:
        return jsonify({"error": "Rating must be 1–5"}), 400

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """INSERT INTO devmarket_reviews (product_id, reviewer_id, rating, title, content)
               VALUES (%s::uuid,%s::uuid,%s,%s,%s) RETURNING *""",
            (pid, uid, int(rating), title, content),
        )
        review = safe_dict(cur.fetchone())

        # recalculate product rating
        cur.execute(
            """UPDATE devmarket_products
               SET rating_avg  = (SELECT AVG(rating)   FROM devmarket_reviews WHERE product_id=%s::uuid),
                   review_count= (SELECT COUNT(*)       FROM devmarket_reviews WHERE product_id=%s::uuid)
               WHERE id=%s::uuid""",
            (pid, pid, pid),
        )
        return jsonify({"review": review}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "You already reviewed this product"}), 409
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/orders", methods=["POST"])
@token_required
def create_order(uid):
    d          = request.get_json() or {}
    product_id = d.get("product_id")
    notes      = d.get("notes", "")

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT seller_id, price, title FROM devmarket_products WHERE id=%s::uuid",
            (product_id,),
        )
        product = cur.fetchone()
        if not product:
            return jsonify({"error": "Product not found"}), 404
        if str(product["seller_id"]) == uid:
            return jsonify({"error": "Cannot purchase your own product"}), 400

        cur.execute(
            """INSERT INTO devmarket_orders (buyer_id, seller_id, product_id, notes)
               VALUES (%s::uuid,%s::uuid,%s::uuid,%s) RETURNING *""",
            (uid, product["seller_id"], product_id, notes),
        )
        order    = safe_dict(cur.fetchone())
        order_id = order["id"]

        # auto-create conversation
        cur.execute(
            """INSERT INTO devmarket_conversations
               (participant_one, participant_two, product_id, order_id)
               VALUES (%s::uuid,%s::uuid,%s::uuid,%s::uuid)
               ON CONFLICT DO NOTHING RETURNING id""",
            (uid, str(product["seller_id"]), product_id, order_id),
        )
        conv = cur.fetchone()
        if conv:
            cur.execute(
                """INSERT INTO devmarket_messages (conversation_id, sender_id, content, message_type)
                   VALUES (%s::uuid,%s::uuid,%s,'system')""",
                (
                    str(conv["id"]), uid,
                    f"Hi! I'm interested in '{product['title']}' listed at ${product['price']}. Can we discuss?",
                ),
            )
        return jsonify({"order": order}), 201
    finally:
        cur.close()
        conn.close()


@app.route("/api/orders")
@token_required
def get_orders(uid):
    role = request.args.get("role", "buyer")
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if role == "buyer":
            cur.execute(
                """SELECT o.*, p.title AS product_title, p.slug AS product_slug,
                          p.images AS product_images,
                          u.username AS seller_username, u.avatar_url AS seller_avatar
                   FROM devmarket_orders o
                   JOIN devmarket_products p ON o.product_id = p.id
                   JOIN devmarket_users    u ON o.seller_id  = u.id
                   WHERE o.buyer_id=%s::uuid ORDER BY o.created_at DESC""",
                (uid,),
            )
        else:
            cur.execute(
                """SELECT o.*, p.title AS product_title, p.slug AS product_slug,
                          u.username AS buyer_username, u.avatar_url AS buyer_avatar
                   FROM devmarket_orders o
                   JOIN devmarket_products p ON o.product_id = p.id
                   JOIN devmarket_users    u ON o.buyer_id   = u.id
                   WHERE o.seller_id=%s::uuid ORDER BY o.created_at DESC""",
                (uid,),
            )
        return jsonify({"orders": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# MESSAGING
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/conversations")
@token_required
def get_conversations(uid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT c.*,
                      p.title AS product_title, p.slug AS product_slug,
                      u1.username AS p1_username, u1.full_name AS p1_name, u1.avatar_url AS p1_avatar,
                      u2.username AS p2_username, u2.full_name AS p2_name, u2.avatar_url AS p2_avatar
               FROM devmarket_conversations c
               LEFT JOIN devmarket_products p ON c.product_id    = p.id
               JOIN      devmarket_users   u1 ON c.participant_one = u1.id
               JOIN      devmarket_users   u2 ON c.participant_two = u2.id
               WHERE c.participant_one=%s::uuid OR c.participant_two=%s::uuid
               ORDER BY c.last_message_at DESC""",
            (uid, uid),
        )
        return jsonify({"conversations": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()


@app.route("/api/conversations/<cid>/messages")
@token_required
def get_messages(uid, cid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT * FROM devmarket_conversations
               WHERE id=%s::uuid AND (participant_one=%s::uuid OR participant_two=%s::uuid)""",
            (cid, uid, uid),
        )
        if not cur.fetchone():
            return jsonify({"error": "Conversation not found"}), 404

        cur.execute(
            """SELECT m.*, u.username, u.full_name, u.avatar_url
               FROM devmarket_messages m
               JOIN devmarket_users u ON m.sender_id = u.id
               WHERE m.conversation_id=%s::uuid AND m.is_deleted=FALSE
               ORDER BY m.created_at ASC""",
            (cid,),
        )
        messages = safe_list(cur.fetchall())

        # mark as read
        cur.execute(
            """UPDATE devmarket_messages SET is_read=TRUE
               WHERE conversation_id=%s::uuid AND sender_id!=%s::uuid""",
            (cid, uid),
        )
        return jsonify({"messages": messages})
    finally:
        cur.close()
        conn.close()


@app.route("/api/conversations/<cid>/messages", methods=["POST"])
@token_required
def send_message(uid, cid):
    d       = request.get_json() or {}
    content = d.get("content", "").strip()
    if not content:
        return jsonify({"error": "Message cannot be empty"}), 400

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT * FROM devmarket_conversations
               WHERE id=%s::uuid AND (participant_one=%s::uuid OR participant_two=%s::uuid)""",
            (cid, uid, uid),
        )
        if not cur.fetchone():
            return jsonify({"error": "Conversation not found"}), 404

        cur.execute(
            """INSERT INTO devmarket_messages (conversation_id, sender_id, content)
               VALUES (%s::uuid,%s::uuid,%s) RETURNING *""",
            (cid, uid, content),
        )
        msg = safe_dict(cur.fetchone())

        cur.execute(
            "UPDATE devmarket_conversations SET last_message=%s, last_message_at=NOW() WHERE id=%s::uuid",
            (content[:100], cid),
        )
        return jsonify({"message": msg}), 201
    finally:
        cur.close()
        conn.close()


@app.route("/api/conversations/start", methods=["POST"])
@token_required
def start_conversation(uid):
    d           = request.get_json() or {}
    other_user  = d.get("recipient_username") or d.get("recipient_id")
    product_id  = d.get("product_id")
    first_msg   = d.get("message", "Hi! I'd like to discuss a product with you.")

    if not other_user:
        return jsonify({"error": "recipient_username or recipient_id required"}), 400

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # resolve recipient
        cur.execute(
            "SELECT id FROM devmarket_users WHERE username=%s OR id::text=%s",
            (other_user, other_user),
        )
        recipient = cur.fetchone()
        if not recipient:
            return jsonify({"error": "Recipient not found"}), 404
        rid = str(recipient["id"])

        # find existing conv between these two
        cur.execute(
            """SELECT id FROM devmarket_conversations
               WHERE (participant_one=%s::uuid AND participant_two=%s::uuid)
                  OR (participant_one=%s::uuid AND participant_two=%s::uuid)
               LIMIT 1""",
            (uid, rid, rid, uid),
        )
        existing = cur.fetchone()

        if existing:
            conv_id = str(existing["id"])
        else:
            prod_uuid = product_id if product_id else None
            cur.execute(
                """INSERT INTO devmarket_conversations
                   (participant_one, participant_two, product_id)
                   VALUES (%s::uuid,%s::uuid,%s)
                   RETURNING id""",
                (uid, rid, prod_uuid),
            )
            conv_id = str(cur.fetchone()["id"])

        # insert first message
        cur.execute(
            """INSERT INTO devmarket_messages (conversation_id, sender_id, content)
               VALUES (%s::uuid,%s::uuid,%s)""",
            (conv_id, uid, first_msg),
        )
        cur.execute(
            "UPDATE devmarket_conversations SET last_message=%s, last_message_at=NOW() WHERE id=%s::uuid",
            (first_msg[:100], conv_id),
        )
        return jsonify({"conversation_id": conv_id}), 201
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/notifications")
@token_required
def get_notifications(uid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM devmarket_notifications WHERE user_id=%s::uuid ORDER BY created_at DESC LIMIT 30",
            (uid,),
        )
        notifs = safe_list(cur.fetchall())
        unread = sum(1 for n in notifs if not n["is_read"])
        return jsonify({"notifications": notifs, "unread": unread})
    finally:
        cur.close()
        conn.close()


@app.route("/api/notifications/read-all", methods=["POST"])
@token_required
def mark_all_read(uid):
    db_execute("UPDATE devmarket_notifications SET is_read=TRUE WHERE user_id=%s::uuid", (uid,))
    return jsonify({"message": "All marked as read"})

# ─────────────────────────────────────────────────────────────────────────────
# USER PROFILES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/users/<username>")
def get_user_profile(username):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT id, username, full_name, bio, avatar_url, cover_url,
                      github_url, website_url, twitter_url, linkedin_url, skills,
                      role, is_verified, reputation_score, total_sales,
                      total_purchases, joined_at, location, badge
               FROM devmarket_users WHERE username=%s""",
            (username,),
        )
        user = cur.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        user = safe_dict(user)

        cur.execute(
            """SELECT id, title, slug, price, images, rating_avg, downloads, product_type
               FROM devmarket_products
               WHERE seller_id=%s::uuid AND is_active=TRUE
               ORDER BY created_at DESC""",
            (user["id"],),
        )
        products = safe_list(cur.fetchall())

        cur.execute(
            "SELECT * FROM devmarket_portfolio WHERE user_id=%s::uuid ORDER BY created_at DESC",
            (user["id"],),
        )
        portfolio = safe_list(cur.fetchall())

        return jsonify({"user": user, "products": products, "portfolio": portfolio})
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/dashboard/stats")
@token_required
def dashboard_stats(uid):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        def scalar(sql, p=()):
            cur.execute(sql, p)
            row = cur.fetchone()
            if not row:
                return 0
            val = list(row.values())[0]
            return int(val) if val is not None else 0

        total_products   = scalar("SELECT COUNT(*)        FROM devmarket_products WHERE seller_id=%s::uuid", (uid,))
        total_views      = scalar("SELECT COALESCE(SUM(views),0)     FROM devmarket_products WHERE seller_id=%s::uuid", (uid,))
        total_downloads  = scalar("SELECT COALESCE(SUM(downloads),0) FROM devmarket_products WHERE seller_id=%s::uuid", (uid,))
        purchases        = scalar("SELECT COUNT(*) FROM devmarket_orders WHERE buyer_id=%s::uuid",  (uid,))
        sales            = scalar("SELECT COUNT(*) FROM devmarket_orders WHERE seller_id=%s::uuid", (uid,))
        conversations    = scalar(
            "SELECT COUNT(*) FROM devmarket_conversations WHERE participant_one=%s::uuid OR participant_two=%s::uuid",
            (uid, uid),
        )

        cur.execute(
            """SELECT title, views, downloads, rating_avg, slug, images
               FROM devmarket_products WHERE seller_id=%s::uuid
               ORDER BY views DESC LIMIT 5""",
            (uid,),
        )
        top_products = safe_list(cur.fetchall())

        return jsonify({
            "total_products":  total_products,
            "total_views":     total_views,
            "total_downloads": total_downloads,
            "purchases":       purchases,
            "sales":           sales,
            "conversations":   conversations,
            "top_products":    top_products,
        })
    finally:
        cur.close()
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/portfolio")
def get_portfolio():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    rows = db_execute(
        "SELECT * FROM devmarket_portfolio WHERE user_id=%s::uuid ORDER BY created_at DESC",
        (user_id,), fetch="all",
    )
    return jsonify({"portfolio": safe_list(rows or [])})


@app.route("/api/portfolio", methods=["POST"])
@token_required
def add_portfolio(uid):
    d   = request.get_json() or {}
    row = db_execute(
        """INSERT INTO devmarket_portfolio (user_id, title, description, image_url, project_url, tech_stack)
           VALUES (%s::uuid,%s,%s,%s,%s,%s) RETURNING *""",
        (uid, d.get("title"), d.get("description"),
         d.get("image_url"), d.get("project_url"), d.get("tech_stack", [])),
        fetch="one",
    )
    return jsonify({"item": safe_dict(row)}), 201

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/articles")
def get_articles():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(50, int(request.args.get("per_page", 10)))
    offset   = (page - 1) * per_page
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT a.*, u.username, u.full_name, u.avatar_url
               FROM devmarket_articles a
               JOIN devmarket_users u ON a.author_id = u.id
               WHERE a.is_published=TRUE
               ORDER BY a.created_at DESC LIMIT %s OFFSET %s""",
            (per_page, offset),
        )
        return jsonify({"articles": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()


@app.route("/api/articles", methods=["POST"])
@token_required
def create_article(uid):
    d = request.get_json() or {}
    if not d.get("title") or not d.get("content"):
        return jsonify({"error": "Title and content required"}), 400
    slug = slugify(d["title"]) + "-" + str(uuid.uuid4())[:8]
    row = db_execute(
        """INSERT INTO devmarket_articles (author_id, title, slug, content, cover_image, tags)
           VALUES (%s::uuid,%s,%s,%s,%s,%s) RETURNING *""",
        (uid, d["title"], slug, d["content"], d.get("cover_image"), d.get("tags", [])),
        fetch="one",
    )
    return jsonify({"article": safe_dict(row)}), 201

# ─────────────────────────────────────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/jobs")
def get_jobs():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(50, int(request.args.get("per_page", 10)))
    offset   = (page - 1) * per_page
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """SELECT j.*, u.username, u.full_name, u.avatar_url
               FROM devmarket_jobs j
               JOIN devmarket_users u ON j.poster_id = u.id
               WHERE j.is_active=TRUE
               ORDER BY j.created_at DESC LIMIT %s OFFSET %s""",
            (per_page, offset),
        )
        return jsonify({"jobs": safe_list(cur.fetchall())})
    finally:
        cur.close()
        conn.close()


@app.route("/api/jobs", methods=["POST"])
@token_required
def post_job(uid):
    d = request.get_json() or {}
    if not d.get("title") or not d.get("description"):
        return jsonify({"error": "Title and description required"}), 400
    row = db_execute(
        """INSERT INTO devmarket_jobs
           (poster_id, title, company, description, job_type, location, salary_range, tech_stack, is_remote)
           VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (uid, d["title"], d.get("company"), d["description"],
         d.get("job_type", "full-time"), d.get("location"),
         d.get("salary_range"), d.get("tech_stack", []), d.get("is_remote", True)),
        fetch="one",
    )
    return jsonify({"job": safe_dict(row)}), 201

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION REQUEST
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/users/request-verification", methods=["POST"])
@token_required
def request_verification(uid):
    db_execute(
        """INSERT INTO devmarket_notifications (user_id, type, title, body)
           VALUES (%s::uuid,'system','Verification Requested',
           'Your seller verification request has been submitted. We will review it within 24 hours.')""",
        (uid,),
    )
    return jsonify({"message": "Verification request submitted"})

# ─────────────────────────────────────────────────────────────────────────────
# AI  (Mistral + Tavily)
# ─────────────────────────────────────────────────────────────────────────────

def tavily_search(query: str, max_results=3):
    try:
        r = requests.post(
            TAVILY_URL,
            json={"api_key": TAVILY_API_KEY, "query": query,
                  "search_depth": "basic", "max_results": max_results,
                  "include_answer": True},
            timeout=10,
        )
        data    = r.json()
        results = []
        if data.get("answer"):
            results.append(f"Direct Answer: {data['answer']}")
        for item in data.get("results", [])[:3]:
            results.append(f"• {item.get('title','')}: {item.get('content','')[:200]}…")
        return "\n".join(results) or None
    except Exception:
        return None


def mistral_chat(messages: list, system_prompt: str = None) -> str:
    all_msgs = []
    if system_prompt:
        all_msgs.append({"role": "system", "content": system_prompt})
    all_msgs.extend(messages)
    try:
        r = requests.post(
            MISTRAL_URL,
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "mistral-small-latest", "messages": all_msgs,
                  "max_tokens": 1000, "temperature": 0.7},
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI temporarily unavailable. ({e})"


@app.route("/api/ai/chat", methods=["POST"])
@optional_auth
def ai_chat(uid):
    d          = request.get_json() or {}
    messages   = d.get("messages", [])
    session_id = d.get("session_id", str(uuid.uuid4()))
    use_search = d.get("use_search", False)

    if not messages:
        return jsonify({"error": "No messages"}), 400

    user_msg   = messages[-1].get("content", "")
    search_ctx = ""
    search_kws = ["latest", "current", "trending", "new", "today", "recent", "2024", "2025"]
    do_search  = use_search or any(kw in user_msg.lower() for kw in search_kws)

    if do_search:
        result = tavily_search(user_msg)
        if result:
            search_ctx = f"\n\nReal-time web results:\n{result}"

    system = (
        "You are Devvy, the AI assistant for Devmarket — the world's premier developer marketplace. "
        "You help developers find tools, APIs, templates, scripts, plugins, datasets, and more. "
        "The platform does not process payments — buyers and sellers negotiate through messaging."
        + search_ctx
    )
    response = mistral_chat(messages, system)

    if uid:
        try:
            db_execute(
                """INSERT INTO devmarket_ai_chats (user_id, session_id, messages)
                   VALUES (%s::uuid,%s,%s) ON CONFLICT DO NOTHING""",
                (uid, session_id,
                 json.dumps(messages + [{"role": "assistant", "content": response}])),
            )
        except Exception:
            pass

    return jsonify({"response": response, "session_id": session_id,
                    "searched": do_search and bool(search_ctx)})


@app.route("/api/ai/search", methods=["POST"])
def ai_search():
    d     = request.get_json() or {}
    query = d.get("query", "")
    if not query:
        return jsonify({"error": "Query required"}), 400
    results = tavily_search(query, max_results=5)
    if not results:
        return jsonify({"results": [], "summary": "No results found"})
    summary = mistral_chat(
        [{"role": "user", "content": f"Summarise for a developer: {results}"}],
        "You are a concise technical assistant."
    )
    return jsonify({"results": results, "summary": summary, "query": query})

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
