# server.py — StartupHive API v3.0
# Flask + PostgreSQL + Cloudinary | All tables: startuphive_
# pip install flask flask-cors psycopg2-binary pyjwt bcrypt cloudinary

from flask import Flask, request, jsonify, g
from flask_cors import CORS
import psycopg2, psycopg2.extras
import jwt, datetime, bcrypt, cloudinary, cloudinary.uploader
import re, json
from functools import wraps

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── CONFIG ────────────────────────────────────────────────────
DB_HOST     = "dpg-d70himndiees73dlbeig-a.frankfurt-postgres.render.com"
DB_NAME     = "trends_db2"
DB_USER     = "trends_db2_user"
DB_PASSWORD = "h5NO8WY8nxLF64WSM7jwYZ7b8B7dCOiR"
DB_PORT     = 5432
CLOUDINARY_CLOUD_NAME = "ddusfl7pi"
CLOUDINARY_API_KEY    = "599965682593626"
CLOUDINARY_API_SECRET = "pUcb90_1jtv-rDlHXRRsfDcBK5k"
JWT_SECRET    = "startuphive_v3_jwt_2025_xK9pLm"
JWT_ALGORITHM = "HS256"

cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME,
                  api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

SIGNAL_TYPES   = ["invest","buy","bid","customer","partner","press"]
STAGES         = ["idea","pre-seed","seed","series-a","bootstrapped","growing","scaling"]
CATEGORIES     = ["AI","Fintech","Climate","Health","SaaS","Consumer","B2B","Marketplace",
                   "Hardware","Education","Developer Tools","Web3","Gaming","Productivity","Media","Other"]
ASK_TYPES      = ["funding","hiring","partners","customers","press","advice"]
UPDATE_TYPES   = ["launch","traction","team","product","fundraising","press","pivot","other"]
VER_LEVELS     = ["unregistered","registered","verified","audited"]
COMMUNITIES    = ["s/general","s/saas","s/startup","s/investors","s/coding","s/consumers","s/web3","s/climate"]

# ── DATABASE ──────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER,
                                password=DB_PASSWORD, port=DB_PORT, sslmode="require")
        g.db.cursor_factory = psycopg2.extras.RealDictCursor
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    db = get_db(); cur = db.cursor()
    ddl = [
        # USERS
        """CREATE TABLE IF NOT EXISTS startuphive_users (
            id SERIAL PRIMARY KEY, name VARCHAR(150) NOT NULL,
            username VARCHAR(60) UNIQUE NOT NULL, email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL, avatar_url VARCHAR(500), cover_url VARCHAR(500),
            bio TEXT, headline VARCHAR(200), website VARCHAR(500),
            twitter VARCHAR(100), linkedin VARCHAR(100), github VARCHAR(100),
            contact_methods JSONB DEFAULT '{}',
            is_verified BOOLEAN DEFAULT FALSE, reputation INTEGER DEFAULT 0,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # STARTUPS
        """CREATE TABLE IF NOT EXISTS startuphive_startups (
            id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            name VARCHAR(150) NOT NULL, slug VARCHAR(180) UNIQUE NOT NULL,
            tagline VARCHAR(300), logo_url VARCHAR(500), cover_url VARCHAR(500),
            status VARCHAR(20) DEFAULT 'unregistered'
                CHECK(status IN('unregistered','registered','verified','audited','for_sale','acquired','inactive')),
            verification_level VARCHAR(20) DEFAULT 'unregistered'
                CHECK(verification_level IN('unregistered','registered','verified','audited')),
            stage VARCHAR(20) DEFAULT 'idea' CHECK(stage IN('idea','pre-seed','seed','series-a','bootstrapped','growing','scaling')),
            categories TEXT[] DEFAULT '{}', needs TEXT[] DEFAULT '{}',
            location_based VARCHAR(150), location_reach JSONB DEFAULT '["Global"]',
            founded_date VARCHAR(20), team_size INTEGER DEFAULT 1,
            demo_url VARCHAR(500), video_url VARCHAR(500), contact_methods JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE, is_featured BOOLEAN DEFAULT FALSE,
            view_count INTEGER DEFAULT 0, upvote_count INTEGER DEFAULT 0,
            bookmark_count INTEGER DEFAULT 0, message_count INTEGER DEFAULT 0,
            signal_score INTEGER DEFAULT 0, last_update_post TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # STARTUP CONTENT
        """CREATE TABLE IF NOT EXISTS startuphive_startup_content (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE UNIQUE,
            about_problem TEXT, about_solution TEXT, about_why_now TEXT,
            about_business_model TEXT, traction_summary TEXT,
            tech_stack TEXT[] DEFAULT '{}', video_url VARCHAR(500), documentation_url VARCHAR(500),
            roadmap_now TEXT, roadmap_next TEXT, roadmap_later TEXT,
            competitors TEXT[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # METRICS
        """CREATE TABLE IF NOT EXISTS startuphive_metrics (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            label VARCHAR(80) NOT NULL, value VARCHAR(80) NOT NULL,
            confidence VARCHAR(20) DEFAULT 'claimed' CHECK(confidence IN('claimed','verified','audited')),
            recorded_at DATE DEFAULT CURRENT_DATE, is_current BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # ASKS
        """CREATE TABLE IF NOT EXISTS startuphive_asks (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            type VARCHAR(20) NOT NULL CHECK(type IN('funding','hiring','partners','customers','press','advice')),
            description VARCHAR(600), urgency VARCHAR(20) DEFAULT 'ongoing'
                CHECK(urgency IN('ongoing','this-month','urgent')),
            is_active BOOLEAN DEFAULT TRUE, response_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # TEAM
        """CREATE TABLE IF NOT EXISTS startuphive_team (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            name VARCHAR(150) NOT NULL, role VARCHAR(100), bio VARCHAR(400),
            avatar_url VARCHAR(500), linkedin VARCHAR(300), twitter VARCHAR(100),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # UPDATES / CHANGELOG
        """CREATE TABLE IF NOT EXISTS startuphive_updates (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            title VARCHAR(300) NOT NULL, content TEXT NOT NULL,
            type VARCHAR(20) DEFAULT 'other' CHECK(type IN('launch','traction','team','product','fundraising','press','pivot','other')),
            is_pinned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # EDIT HISTORY
        """CREATE TABLE IF NOT EXISTS startuphive_history (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            field_name VARCHAR(80), old_value TEXT, new_value TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # SIGNALS (invest/buy/bid/customer/partner/press interest)
        """CREATE TABLE IF NOT EXISTS startuphive_signals (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            signal_type VARCHAR(20) NOT NULL CHECK(signal_type IN('invest','buy','bid','customer','partner','press')),
            amount BIGINT, currency VARCHAR(10) DEFAULT 'USD', message TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(startup_id, user_id, signal_type))""",

        # REVIEWS
        """CREATE TABLE IF NOT EXISTS startuphive_reviews (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            rating INTEGER CHECK(rating BETWEEN 1 AND 5),
            title VARCHAR(200), content TEXT,
            helpful_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(startup_id, user_id))""",

        # REVIEW REPLIES
        """CREATE TABLE IF NOT EXISTS startuphive_review_replies (
            id SERIAL PRIMARY KEY,
            review_id INTEGER REFERENCES startuphive_reviews(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # UPVOTES
        """CREATE TABLE IF NOT EXISTS startuphive_upvotes (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(startup_id, user_id))""",

        # BOOKMARKS
        """CREATE TABLE IF NOT EXISTS startuphive_bookmarks (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(startup_id, user_id))""",

        # FOLLOWS
        """CREATE TABLE IF NOT EXISTS startuphive_follows (
            id SERIAL PRIMARY KEY,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(startup_id, user_id))""",

        # COMMUNITY POSTS
        """CREATE TABLE IF NOT EXISTS startuphive_community_posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            community VARCHAR(40) NOT NULL, title VARCHAR(300),
            content TEXT, media_url VARCHAR(500), media_type VARCHAR(10) DEFAULT 'text'
                CHECK(media_type IN('text','image','video')),
            upvote_count INTEGER DEFAULT 0, downvote_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0, is_pinned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # COMMUNITY VOTES
        """CREATE TABLE IF NOT EXISTS startuphive_community_votes (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES startuphive_community_posts(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            vote_type VARCHAR(4) CHECK(vote_type IN('up','down')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(post_id, user_id))""",

        # COMMUNITY COMMENTS
        """CREATE TABLE IF NOT EXISTS startuphive_community_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES startuphive_community_posts(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES startuphive_community_comments(id) ON DELETE CASCADE,
            content TEXT NOT NULL, like_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # MESSAGES / CHATS
        """CREATE TABLE IF NOT EXISTS startuphive_conversations (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        """CREATE TABLE IF NOT EXISTS startuphive_conversation_members (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES startuphive_conversations(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            last_read_at TIMESTAMP,
            UNIQUE(conversation_id, user_id))""",

        """CREATE TABLE IF NOT EXISTS startuphive_messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES startuphive_conversations(id) ON DELETE CASCADE,
            sender_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            content TEXT NOT NULL, media_url VARCHAR(500), media_type VARCHAR(10),
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # NOTIFICATIONS
        """CREATE TABLE IF NOT EXISTS startuphive_notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            type VARCHAR(40) NOT NULL,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES startuphive_community_posts(id) ON DELETE CASCADE,
            message TEXT, link VARCHAR(500), is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",

        # ACTIVITY
        """CREATE TABLE IF NOT EXISTS startuphive_activity (
            id SERIAL PRIMARY KEY, type VARCHAR(40) NOT NULL,
            user_id INTEGER REFERENCES startuphive_users(id) ON DELETE SET NULL,
            startup_id INTEGER REFERENCES startuphive_startups(id) ON DELETE CASCADE,
            meta JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    ]
    for stmt in ddl: cur.execute(stmt)

    idx = [
        "CREATE INDEX IF NOT EXISTS idx3_s_slug      ON startuphive_startups(slug)",
        "CREATE INDEX IF NOT EXISTS idx3_s_user      ON startuphive_startups(user_id)",
        "CREATE INDEX IF NOT EXISTS idx3_s_active    ON startuphive_startups(is_active, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx3_s_upvotes   ON startuphive_startups(upvote_count DESC)",
        "CREATE INDEX IF NOT EXISTS idx3_uv_s        ON startuphive_upvotes(startup_id)",
        "CREATE INDEX IF NOT EXISTS idx3_uv_u        ON startuphive_upvotes(user_id)",
        "CREATE INDEX IF NOT EXISTS idx3_bk_u        ON startuphive_bookmarks(user_id)",
        "CREATE INDEX IF NOT EXISTS idx3_sig_s       ON startuphive_signals(startup_id)",
        "CREATE INDEX IF NOT EXISTS idx3_rev_s       ON startuphive_reviews(startup_id)",
        "CREATE INDEX IF NOT EXISTS idx3_cp_comm     ON startuphive_community_posts(community, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx3_cv_post     ON startuphive_community_votes(post_id)",
        "CREATE INDEX IF NOT EXISTS idx3_cc_post     ON startuphive_community_comments(post_id)",
        "CREATE INDEX IF NOT EXISTS idx3_msg_conv    ON startuphive_messages(conversation_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx3_notif_u     ON startuphive_notifications(user_id, is_read)",
        "CREATE INDEX IF NOT EXISTS idx3_act_ts      ON startuphive_activity(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx3_hist_s      ON startuphive_history(startup_id, changed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx3_upd_s       ON startuphive_updates(startup_id, created_at DESC)",
    ]
    for stmt in idx: cur.execute(stmt)
    # Migrations for existing DBs — add missing columns safely
    migrations = [
        "ALTER TABLE startuphive_startup_content ADD COLUMN IF NOT EXISTS video_url VARCHAR(500)",
        "ALTER TABLE startuphive_startup_content ADD COLUMN IF NOT EXISTS competitors TEXT[] DEFAULT '{}'",
    ]
    for m in migrations:
        try: cur.execute(m)
        except Exception: db.rollback()
    db.commit(); cur.close()
    print("✅ startuphive_ schema v3 ready — 22 tables")

# ── HELPERS ───────────────────────────────────────────────────
def make_token(uid):
    return jwt.encode({"user_id": uid, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)},
                      JWT_SECRET, algorithm=JWT_ALGORITHM)

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:140]

def sj(v):
    if isinstance(v, (dict, list)): return v
    if isinstance(v, str):
        try: return json.loads(v)
        except: return {}
    return {} if v is None else v

def sa(v):
    if isinstance(v, list): return v
    if isinstance(v, str):
        try: return json.loads(v)
        except: return []
    return []

def log_act(atype, uid=None, sid=None, meta=None):
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("INSERT INTO startuphive_activity(type,user_id,startup_id,meta) VALUES(%s,%s,%s,%s)",
                    (atype, uid, sid, json.dumps(meta or {})))
        db.commit(); cur.close()
    except: pass

def notify(uid, actor_id, ntype, sid=None, pid=None, message="", link=""):
    if uid == actor_id: return
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("""INSERT INTO startuphive_notifications
                       (user_id,actor_id,type,startup_id,post_id,message,link)
                       VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (uid, actor_id, ntype, sid, pid, message, link))
        db.commit(); cur.close()
    except: pass

def token_required(f):
    @wraps(f)
    def dec(*a, **kw):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "): return jsonify({"error":"Token required"}), 401
        try:
            d = jwt.decode(auth.split(" ",1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            g.uid = d["user_id"]
        except jwt.ExpiredSignatureError: return jsonify({"error":"Token expired"}), 401
        except: return jsonify({"error":"Invalid token"}), 401
        return f(*a, **kw)
    return dec

def optional_token(f):
    @wraps(f)
    def dec(*a, **kw):
        g.uid = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                d = jwt.decode(auth.split(" ",1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
                g.uid = d["user_id"]
            except: pass
        return f(*a, **kw)
    return dec

def fmt_startup(r, upvoted=False, bookmarked=False, following=False):
    return {
        "id": r["id"], "name": r["name"], "slug": r["slug"],
        "tagline": r.get("tagline") or "", "logo_url": r.get("logo_url") or "",
        "cover_url": r.get("cover_url") or "",
        "status": r.get("status") or "unregistered",
        "verification_level": r.get("verification_level") or "unregistered",
        "stage": r.get("stage") or "idea",
        "categories": sa(r.get("categories")), "needs": sa(r.get("needs")),
        "location_based": r.get("location_based") or "",
        "location_reach": sa(r.get("location_reach")) or ["Global"],
        "founded_date": r.get("founded_date") or "",
        "team_size": r.get("team_size") or 1,
        "demo_url": r.get("demo_url") or "", "video_url": r.get("video_url") or "",
        "contact_methods": sj(r.get("contact_methods")),
        "is_active": r.get("is_active", True), "is_featured": r.get("is_featured", False),
        "view_count": r.get("view_count") or 0, "upvote_count": r.get("upvote_count") or 0,
        "bookmark_count": r.get("bookmark_count") or 0, "message_count": r.get("message_count") or 0,
        "signal_score": r.get("signal_score") or 0,
        "owner_id": r.get("user_id"), "owner_name": r.get("owner_name") or "",
        "owner_username": r.get("owner_username") or "", "owner_avatar": r.get("owner_avatar") or "",
        "upvoted": upvoted, "bookmarked": bookmarked, "following": following,
        "last_update_post": r["last_update_post"].isoformat() if r.get("last_update_post") else None,
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
    }

def fmt_user(u):
    return {
        "id": u["id"], "name": u["name"], "username": u["username"],
        "email": u.get("email") or "", "avatar_url": u.get("avatar_url") or "",
        "cover_url": u.get("cover_url") or "", "bio": u.get("bio") or "",
        "headline": u.get("headline") or "", "website": u.get("website") or "",
        "twitter": u.get("twitter") or "", "linkedin": u.get("linkedin") or "",
        "github": u.get("github") or "", "contact_methods": sj(u.get("contact_methods")),
        "is_verified": u.get("is_verified", False), "reputation": u.get("reputation") or 0,
        "last_active": u["last_active"].isoformat() if u.get("last_active") else None,
        "created_at": u["created_at"].isoformat() if u.get("created_at") else None,
    }

# ── AUTH ──────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.get_json() or {}
    name = d.get("name","").strip(); email = d.get("email","").lower().strip(); pw = d.get("password","")
    username = d.get("username","").lower().strip()
    if not name or not email or not pw: return jsonify({"error":"Name, email and password required"}), 400
    if len(pw) < 8: return jsonify({"error":"Password min 8 chars"}), 400
    if not username: username = re.sub(r"[^a-z0-9_]","",re.sub(r"\s+","_",name.lower()))[:28] or "user"
    if not re.match(r"^[a-z0-9_]{2,40}$", username): return jsonify({"error":"Invalid username"}), 400
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id FROM startuphive_users WHERE email=%s OR username=%s", (email, username))
    if cur.fetchone(): cur.close(); return jsonify({"error":"Email or username taken"}), 409
    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    cur.execute("INSERT INTO startuphive_users(name,username,email,password_hash) VALUES(%s,%s,%s,%s) RETURNING id",
                (name, username, email, pw_hash))
    uid = cur.fetchone()["id"]; db.commit(); cur.close()
    log_act("user_joined", uid)
    return jsonify({"token": make_token(uid), "user": {"id":uid,"name":name,"username":username,"email":email,"avatar_url":""}}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    identifier = d.get("identifier","").lower().strip(); pw = d.get("password","")
    if not identifier or not pw: return jsonify({"error":"Credentials required"}), 400
    db = get_db(); cur = db.cursor()
    cur.execute("""SELECT id,name,username,email,password_hash,avatar_url,bio,headline,
                          contact_methods,website,twitter,linkedin,github,is_verified,reputation,last_active,created_at
                   FROM startuphive_users WHERE email=%s OR username=%s""", (identifier, identifier))
    u = cur.fetchone(); cur.close()
    if not u or not bcrypt.checkpw(pw.encode(), u["password_hash"].encode()):
        return jsonify({"error":"Invalid credentials"}), 401
    c = get_db().cursor()
    c.execute("UPDATE startuphive_users SET last_active=NOW() WHERE id=%s", (u["id"],))
    get_db().commit(); c.close()
    return jsonify({"token": make_token(u["id"]), "user": fmt_user(u)})

@app.route("/api/auth/me", methods=["GET"])
@token_required
def get_me():
    db = get_db(); cur = db.cursor()
    cur.execute("""SELECT id,name,username,email,avatar_url,cover_url,bio,headline,contact_methods,
                          website,twitter,linkedin,github,is_verified,reputation,last_active,created_at
                   FROM startuphive_users WHERE id=%s""", (g.uid,))
    u = cur.fetchone()
    if not u: cur.close(); return jsonify({"error":"Not found"}), 404
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE user_id=%s AND is_active=TRUE", (g.uid,))
    sc = cur.fetchone()["c"]; cur.close()
    res = fmt_user(u); res["startup_count"] = sc; return jsonify(res)

@app.route("/api/auth/profile", methods=["PUT"])
@token_required
def update_profile():
    d = request.get_json() or {}
    allowed = ["name","bio","headline","avatar_url","cover_url","website","twitter","linkedin","github","contact_methods"]
    updates = {k:v for k,v in d.items() if k in allowed}
    if "contact_methods" in updates: updates["contact_methods"] = json.dumps(updates["contact_methods"])
    if not updates: return jsonify({"error":"No fields"}), 400
    db = get_db(); cur = db.cursor()
    sets = ", ".join(f"{k}=%s" for k in updates)
    cur.execute(f"UPDATE startuphive_users SET {sets},updated_at=NOW() WHERE id=%s", list(updates.values())+[g.uid])
    db.commit(); cur.close(); return jsonify({"success":True})

@app.route("/api/auth/password", methods=["PUT"])
@token_required
def change_password():
    d = request.get_json() or {}
    old = d.get("old_password",""); new = d.get("new_password","")
    if len(new) < 8: return jsonify({"error":"Min 8 chars"}), 400
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT password_hash FROM startuphive_users WHERE id=%s", (g.uid,))
    u = cur.fetchone()
    if not u or not bcrypt.checkpw(old.encode(), u["password_hash"].encode()):
        cur.close(); return jsonify({"error":"Wrong current password"}), 401
    new_hash = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
    cur.execute("UPDATE startuphive_users SET password_hash=%s WHERE id=%s", (new_hash, g.uid))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── UPLOAD ────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
@token_required
def upload_file():
    if "file" not in request.files: return jsonify({"error":"No file"}), 400
    f = request.files["file"]; kind = request.form.get("kind","logo")
    folders = {"logo":"startuphive/logos","cover":"startuphive/covers","avatar":"startuphive/avatars","media":"startuphive/media","doc":"startuphive/docs"}
    try:
        res = cloudinary.uploader.upload(f, folder=folders.get(kind,"startuphive/misc"),
              transformation=[{"width":800,"crop":"limit","quality":"auto:good","fetch_format":"auto"}])
        return jsonify({"url":res["secure_url"],"public_id":res["public_id"]})
    except Exception as e: return jsonify({"error":str(e)}), 500

# ── STARTUPS — MARQUEE ────────────────────────────────────────
@app.route("/api/startups/marquee", methods=["GET"])
def marquee():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id,name,slug,verification_level FROM startuphive_startups WHERE is_active=TRUE ORDER BY updated_at DESC LIMIT 50")
    rows = cur.fetchall(); cur.close()
    return jsonify([{"id":r["id"],"name":r["name"],"slug":r["slug"],"level":r["verification_level"]} for r in rows])

# ── STARTUPS — LIST ───────────────────────────────────────────
@app.route("/api/startups", methods=["GET"])
@optional_token
def list_startups():
    page=max(1,request.args.get("page",1,type=int)); per_page=min(40,max(8,request.args.get("per_page",20,type=int)))
    sort=request.args.get("sort","recent"); q=request.args.get("q","").strip()
    category=request.args.get("category",""); stage=request.args.get("stage","")
    need=request.args.get("need",""); featured=request.args.get("featured","")
    conditions=["s.is_active=TRUE"]; params=[]
    if q:
        conditions.append("(s.name ILIKE %s OR s.tagline ILIKE %s OR %s=ANY(s.categories))")
        lq=f"%{q}%"; params+=[lq,lq,q]
    if category: conditions.append("%s=ANY(s.categories)"); params.append(category)
    if stage: conditions.append("s.stage=%s"); params.append(stage)
    if featured: conditions.append("s.is_featured=TRUE")
    need_join=""
    if need: need_join="JOIN startuphive_asks ak ON ak.startup_id=s.id AND ak.is_active=TRUE AND ak.type=%s"; params.insert(0,need)
    where="WHERE "+" AND ".join(conditions)
    order={"recent":"s.created_at DESC","trending":"s.upvote_count DESC,s.signal_score DESC,s.created_at DESC",
           "active":"s.updated_at DESC","views":"s.view_count DESC"}.get(sort,"s.created_at DESC")
    offset=(page-1)*per_page; db=get_db(); cur=db.cursor()
    cur.execute(f"""SELECT s.*,u.name AS owner_name,u.username AS owner_username,u.avatar_url AS owner_avatar
                    FROM startuphive_startups s {need_join} LEFT JOIN startuphive_users u ON s.user_id=u.id
                    {where} ORDER BY {order} LIMIT %s OFFSET %s""",
                ([need]+params[1:] if need else params)+[per_page,offset])
    rows=cur.fetchall()
    cur.execute(f"SELECT COUNT(*) AS t FROM startuphive_startups s {need_join} {where}",
                [need]+params[1:] if need else params)
    total=cur.fetchone()["t"]; uv=bk=set()
    if g.uid and rows:
        ids=[r["id"] for r in rows]
        cur.execute("SELECT startup_id FROM startuphive_upvotes   WHERE user_id=%s AND startup_id=ANY(%s)",(g.uid,ids)); uv={r["startup_id"] for r in cur.fetchall()}
        cur.execute("SELECT startup_id FROM startuphive_bookmarks WHERE user_id=%s AND startup_id=ANY(%s)",(g.uid,ids)); bk={r["startup_id"] for r in cur.fetchall()}
    cur.close()
    return jsonify({"startups":[fmt_startup(r,r["id"] in uv,r["id"] in bk) for r in rows],
                    "total":total,"page":page,"per_page":per_page,"pages":max(1,-(-total//per_page))})

# ── STARTUPS — GET SINGLE ─────────────────────────────────────
@app.route("/api/startups/<slug>", methods=["GET"])
@optional_token
def get_startup(slug):
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT s.*,u.name AS owner_name,u.username AS owner_username,
                   u.avatar_url AS owner_avatar,u.bio AS owner_bio,u.headline AS owner_headline,
                   u.twitter AS owner_twitter,u.linkedin AS owner_linkedin,u.website AS owner_website
                   FROM startuphive_startups s LEFT JOIN startuphive_users u ON s.user_id=u.id
                   WHERE s.slug=%s""", (slug,))
    s=cur.fetchone()
    if not s: cur.close(); return jsonify({"error":"Not found"}), 404
    cur.execute("UPDATE startuphive_startups SET view_count=view_count+1 WHERE id=%s",(s["id"],)); get_db().commit()
    uv=bk=fw=False
    if g.uid:
        cur.execute("SELECT 1 FROM startuphive_upvotes   WHERE startup_id=%s AND user_id=%s",(s["id"],g.uid)); uv=bool(cur.fetchone())
        cur.execute("SELECT 1 FROM startuphive_bookmarks WHERE startup_id=%s AND user_id=%s",(s["id"],g.uid)); bk=bool(cur.fetchone())
        cur.execute("SELECT 1 FROM startuphive_follows   WHERE startup_id=%s AND user_id=%s",(s["id"],g.uid)); fw=bool(cur.fetchone())
    cur.execute("SELECT * FROM startuphive_startup_content WHERE startup_id=%s",(s["id"],)); content=cur.fetchone()
    cur.execute("SELECT * FROM startuphive_metrics WHERE startup_id=%s AND is_current=TRUE ORDER BY recorded_at DESC",(s["id"],)); metrics=cur.fetchall()
    cur.execute("SELECT * FROM startuphive_asks WHERE startup_id=%s AND is_active=TRUE ORDER BY urgency DESC,created_at",(s["id"],)); asks=cur.fetchall()
    cur.execute("SELECT * FROM startuphive_team WHERE startup_id=%s ORDER BY sort_order,id",(s["id"],)); team=cur.fetchall()
    cur.execute("SELECT * FROM startuphive_updates WHERE startup_id=%s ORDER BY is_pinned DESC,created_at DESC LIMIT 20",(s["id"],)); updates=cur.fetchall()
    cur.execute("SELECT * FROM startuphive_history WHERE startup_id=%s ORDER BY changed_at DESC LIMIT 2",(s["id"],)); history=cur.fetchall()
    cur.execute("SELECT signal_type,COUNT(*) AS c FROM startuphive_signals WHERE startup_id=%s AND is_active=TRUE GROUP BY signal_type",(s["id"],)); sig_counts={r["signal_type"]:r["c"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_follows WHERE startup_id=%s",(s["id"],)); follower_count=cur.fetchone()["c"]
    cur.execute("SELECT AVG(rating) AS avg,COUNT(*) AS cnt FROM startuphive_reviews WHERE startup_id=%s",(s["id"],)); rev=cur.fetchone()
    cur.close()
    result=fmt_startup(s,uv,bk,fw)
    result.update({"owner_bio":s.get("owner_bio") or "","owner_headline":s.get("owner_headline") or "",
                   "owner_twitter":s.get("owner_twitter") or "","owner_linkedin":s.get("owner_linkedin") or "",
                   "owner_website":s.get("owner_website") or "","follower_count":follower_count,
                   "signal_counts":sig_counts,"avg_rating":float(rev["avg"] or 0),"review_count":rev["cnt"] or 0,
                   "content":{**{"about_problem":"","about_solution":"","about_why_now":"","about_business_model":"",
                               "traction_summary":"","tech_stack":[],"documentation_url":"",
                               "roadmap_now":"","roadmap_next":"","roadmap_later":"","competitors":[]},
                              **({"about_problem":content.get("about_problem") or "","about_solution":content.get("about_solution") or "",
                                  "about_why_now":content.get("about_why_now") or "","about_business_model":content.get("about_business_model") or "",
                                  "traction_summary":content.get("traction_summary") or "","tech_stack":sa(content.get("tech_stack")),
                                  "documentation_url":content.get("documentation_url") or "","roadmap_now":content.get("roadmap_now") or "",
                                  "roadmap_next":content.get("roadmap_next") or "","roadmap_later":content.get("roadmap_later") or "",
                                  "competitors":sa(content.get("competitors"))} if content else {})},
                   "metrics":[{"id":m["id"],"label":m["label"],"value":m["value"],"confidence":m["confidence"],"recorded_at":str(m["recorded_at"])} for m in metrics],
                   "asks":[{"id":a["id"],"type":a["type"],"description":a.get("description") or "","urgency":a["urgency"],"response_count":a["response_count"]} for a in asks],
                   "team":[{"id":t["id"],"name":t["name"],"role":t.get("role") or "","bio":t.get("bio") or "","avatar_url":t.get("avatar_url") or "","linkedin":t.get("linkedin") or ""} for t in team],
                   "updates":[{"id":u["id"],"title":u["title"],"content":u["content"],"type":u["type"],"is_pinned":u["is_pinned"],"created_at":u["created_at"].isoformat()} for u in updates],
                   "history":[{"field":h["field_name"],"old":h.get("old_value") or "","new":h.get("new_value") or "","changed_at":h["changed_at"].isoformat()} for h in history]})
    return jsonify(result)

# ── STARTUPS — CREATE ─────────────────────────────────────────
@app.route("/api/startups", methods=["POST"])
@token_required
def create_startup():
    d=request.get_json() or {}; name=d.get("name","").strip()
    if not name: return jsonify({"error":"Name required"}), 400
    db=get_db(); cur=db.cursor()
    base=slugify(name); slug=base; n=1
    while True:
        cur.execute("SELECT id FROM startuphive_startups WHERE slug=%s",(slug,))
        if not cur.fetchone(): break
        slug=f"{base}-{n}"; n+=1
    categories=[c for c in d.get("categories",[]) if c in CATEGORIES][:5]
    stage=d.get("stage","idea") if d.get("stage") in STAGES else "idea"
    tagline=(d.get("tagline") or name)[:300]
    cur.execute("""INSERT INTO startuphive_startups
        (user_id,name,slug,tagline,categories,stage,status,verification_level,
         location_based,location_reach,founded_date,team_size,demo_url,video_url,
         contact_methods,logo_url,cover_url,needs)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (g.uid,name,slug,tagline,categories,stage,
         d.get("status","unregistered"),d.get("verification_level","unregistered"),
         d.get("location_based",""),json.dumps(d.get("location_reach",["Global"])),
         d.get("founded_date",""),d.get("team_size",1),d.get("demo_url",""),
         d.get("video_url",""),json.dumps(d.get("contact_methods",{})),
         d.get("logo_url","") or "",d.get("cover_url","") or "",
         [str(x) for x in d.get("needs",[]) if x] if d.get("needs") else []))
    sid=cur.fetchone()["id"]
    c=d.get("content",{})
    # Ensure tech_stack is a proper list of strings
    ts = c.get("tech_stack",[])
    if isinstance(ts, str): ts = [x.strip() for x in ts.split(',') if x.strip()]
    elif not isinstance(ts, list): ts = []
    cur.execute("""INSERT INTO startuphive_startup_content
        (startup_id,about_problem,about_solution,about_why_now,about_business_model,
         traction_summary,tech_stack,video_url,documentation_url,roadmap_now,roadmap_next,roadmap_later)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (sid,
         c.get("about_problem","") or "",
         c.get("about_solution","") or "",
         c.get("about_why_now","") or "",
         c.get("about_business_model","") or "",
         c.get("traction_summary","") or "",
         ts,
         c.get("video_url","") or "",
         c.get("documentation_url","") or "",
         c.get("roadmap_now","") or "",
         c.get("roadmap_next","") or "",
         c.get("roadmap_later","") or ""))
    db.commit(); cur.close()
    log_act("startup_listed",g.uid,sid,{"name":name})
    return jsonify({"success":True,"id":sid,"slug":slug}), 201

# ── STARTUPS — UPDATE ─────────────────────────────────────────
@app.route("/api/startups/<int:sid>", methods=["PUT"])
@token_required
def update_startup(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row: cur.close(); return jsonify({"error":"Not found"}), 404
    if row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    d=request.get_json() or {}
    allowed=["name","tagline","categories","stage","status","verification_level","location_based",
             "location_reach","founded_date","team_size","demo_url","video_url","contact_methods",
             "logo_url","cover_url","is_active","needs"]
    updates={k:v for k,v in d.items() if k in allowed}
    for k in ("contact_methods","location_reach"):
        if k in updates and isinstance(updates[k],(dict,list)): updates[k]=json.dumps(updates[k])
    if updates:
        for field in ["stage","status","team_size"]:
            if field in updates:
                cur.execute(f"SELECT {field} FROM startuphive_startups WHERE id=%s",(sid,))
                old=cur.fetchone()
                if old: cur.execute("INSERT INTO startuphive_history(startup_id,user_id,field_name,old_value,new_value) VALUES(%s,%s,%s,%s,%s)",(sid,g.uid,field,str(old[field] or ""),str(updates[field] or "")))
        sets=", ".join(f"{k}=%s" for k in updates)
        cur.execute(f"UPDATE startuphive_startups SET {sets},updated_at=NOW() WHERE id=%s",list(updates.values())+[sid])
    c=d.get("content")
    if c:
        ca=["about_problem","about_solution","about_why_now","about_business_model","traction_summary","tech_stack","video_url","documentation_url","roadmap_now","roadmap_next","roadmap_later","competitors"]
        cu={k:v for k,v in c.items() if k in ca}
        if cu:
            cur.execute("SELECT id FROM startuphive_startup_content WHERE startup_id=%s",(sid,))
            if cur.fetchone():
                s2=", ".join(f"{k}=%s" for k in cu)
                cur.execute(f"UPDATE startuphive_startup_content SET {s2},updated_at=NOW() WHERE startup_id=%s",list(cu.values())+[sid])
            else:
                cur.execute("INSERT INTO startuphive_startup_content(startup_id) VALUES(%s)",(sid,))
                s2=", ".join(f"{k}=%s" for k in cu)
                cur.execute(f"UPDATE startuphive_startup_content SET {s2} WHERE startup_id=%s",list(cu.values())+[sid])
    db.commit(); cur.close(); return jsonify({"success":True})

@app.route("/api/startups/<int:sid>", methods=["DELETE"])
@token_required
def delete_startup(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row: cur.close(); return jsonify({"error":"Not found"}), 404
    if row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    cur.execute("UPDATE startuphive_startups SET is_active=FALSE WHERE id=%s",(sid,))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── UPVOTES ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/upvote", methods=["POST"])
@token_required
def upvote(sid):
    db=get_db(); cur=db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_upvotes(startup_id,user_id) VALUES(%s,%s)",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET upvote_count=upvote_count+1,signal_score=signal_score+2 WHERE id=%s",(sid,))
        cur.execute("UPDATE startuphive_users SET reputation=reputation+1 WHERE id=(SELECT user_id FROM startuphive_startups WHERE id=%s)",(sid,))
        db.commit(); cur.close(); log_act("upvote",g.uid,sid); return jsonify({"upvoted":True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_upvotes WHERE startup_id=%s AND user_id=%s",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET upvote_count=GREATEST(0,upvote_count-1),signal_score=GREATEST(0,signal_score-2) WHERE id=%s",(sid,))
        cur.execute("UPDATE startuphive_users SET reputation=GREATEST(0,reputation-1) WHERE id=(SELECT user_id FROM startuphive_startups WHERE id=%s)",(sid,))
        db.commit(); cur.close(); return jsonify({"upvoted":False})

# ── BOOKMARKS ─────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/bookmark", methods=["POST"])
@token_required
def bookmark(sid):
    db=get_db(); cur=db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_bookmarks(startup_id,user_id) VALUES(%s,%s)",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET bookmark_count=bookmark_count+1 WHERE id=%s",(sid,))
        db.commit(); cur.close(); return jsonify({"bookmarked":True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_bookmarks WHERE startup_id=%s AND user_id=%s",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET bookmark_count=GREATEST(0,bookmark_count-1) WHERE id=%s",(sid,))
        db.commit(); cur.close(); return jsonify({"bookmarked":False})

@app.route("/api/me/bookmarks", methods=["GET"])
@token_required
def my_bookmarks():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT s.*,u.name AS owner_name,u.username AS owner_username,u.avatar_url AS owner_avatar
                   FROM startuphive_startups s JOIN startuphive_bookmarks b ON b.startup_id=s.id
                   LEFT JOIN startuphive_users u ON s.user_id=u.id WHERE b.user_id=%s ORDER BY b.created_at DESC""",(g.uid,))
    rows=cur.fetchall(); cur.close(); return jsonify([fmt_startup(r,bookmarked=True) for r in rows])

# ── FOLLOWS ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/follow", methods=["POST"])
@token_required
def follow_startup(sid):
    db=get_db(); cur=db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_follows(startup_id,user_id) VALUES(%s,%s)",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET signal_score=signal_score+1 WHERE id=%s",(sid,))
        db.commit(); cur.close(); return jsonify({"following":True})
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_follows WHERE startup_id=%s AND user_id=%s",(sid,g.uid))
        cur.execute("UPDATE startuphive_startups SET signal_score=GREATEST(0,signal_score-1) WHERE id=%s",(sid,))
        db.commit(); cur.close(); return jsonify({"following":False})

# ── SIGNALS ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/signal", methods=["POST"])
@token_required
def signal_startup(sid):
    d=request.get_json() or {}; stype=d.get("signal_type","")
    if stype not in SIGNAL_TYPES: return jsonify({"error":"Invalid signal type"}), 400
    db=get_db(); cur=db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_signals(startup_id,user_id,signal_type,amount,currency,message) VALUES(%s,%s,%s,%s,%s,%s)",
                    (sid,g.uid,stype,d.get("amount"),d.get("currency","USD"),d.get("message","")))
        cur.execute("UPDATE startuphive_startups SET signal_score=signal_score+3 WHERE id=%s",(sid,))
        db.commit()
        cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,))
        owner=cur.fetchone()
        if owner: notify(owner["user_id"],g.uid,f"signal_{stype}",sid,message=f"Someone signalled {stype} interest")
        cur.close(); return jsonify({"success":True,"signal_type":stype}), 201
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        cur.execute("DELETE FROM startuphive_signals WHERE startup_id=%s AND user_id=%s AND signal_type=%s",(sid,g.uid,stype))
        cur.execute("UPDATE startuphive_startups SET signal_score=GREATEST(0,signal_score-3) WHERE id=%s",(sid,))
        db.commit(); cur.close(); return jsonify({"success":True,"signal_type":None})

@app.route("/api/startups/<int:sid>/signals", methods=["GET"])
def get_signals(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT s.*,u.name AS user_name,u.username AS user_username,u.avatar_url AS user_avatar
                   FROM startuphive_signals s JOIN startuphive_users u ON s.user_id=u.id
                   WHERE s.startup_id=%s AND s.is_active=TRUE ORDER BY s.created_at DESC""",(sid,))
    rows=cur.fetchall(); cur.close()
    return jsonify([{"id":r["id"],"type":r["signal_type"],"amount":r["amount"],"currency":r["currency"],
                     "message":r["message"] or "","user_name":r["user_name"],"user_username":r["user_username"],
                     "user_avatar":r["user_avatar"] or "","created_at":r["created_at"].isoformat()} for r in rows])

# ── REVIEWS ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/reviews", methods=["GET"])
def get_reviews(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT r.*,u.name AS reviewer_name,u.username AS reviewer_username,u.avatar_url AS reviewer_avatar
                   FROM startuphive_reviews r JOIN startuphive_users u ON r.user_id=u.id
                   WHERE r.startup_id=%s ORDER BY r.created_at DESC""",(sid,))
    reviews=cur.fetchall()
    result=[]
    for rv in reviews:
        cur.execute("""SELECT rp.*,u.name AS replier_name,u.avatar_url AS replier_avatar
                       FROM startuphive_review_replies rp JOIN startuphive_users u ON rp.user_id=u.id
                       WHERE rp.review_id=%s ORDER BY rp.created_at""",(rv["id"],))
        replies=cur.fetchall()
        result.append({"id":rv["id"],"rating":rv["rating"],"title":rv.get("title") or "",
                       "content":rv.get("content") or "","helpful_count":rv["helpful_count"],
                       "reviewer_name":rv["reviewer_name"],"reviewer_username":rv["reviewer_username"],
                       "reviewer_avatar":rv.get("reviewer_avatar") or "","created_at":rv["created_at"].isoformat(),
                       "replies":[{"id":rp["id"],"content":rp["content"],"replier_name":rp["replier_name"],
                                   "replier_avatar":rp.get("replier_avatar") or "","created_at":rp["created_at"].isoformat()} for rp in replies]})
    cur.close(); return jsonify(result)

@app.route("/api/startups/<int:sid>/reviews", methods=["POST"])
@token_required
def post_review(sid):
    d=request.get_json() or {}; rating=d.get("rating")
    if not rating or rating not in range(1,6): return jsonify({"error":"Rating 1-5 required"}), 400
    db=get_db(); cur=db.cursor()
    try:
        cur.execute("INSERT INTO startuphive_reviews(startup_id,user_id,rating,title,content) VALUES(%s,%s,%s,%s,%s)",
                    (sid,g.uid,rating,d.get("title",""),d.get("content","")))
        db.commit()
        cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,))
        owner=cur.fetchone()
        if owner: notify(owner["user_id"],g.uid,"review",sid,message="New review on your startup")
        cur.close(); return jsonify({"success":True}), 201
    except psycopg2.errors.UniqueViolation:
        db.rollback(); cur.close(); return jsonify({"error":"Already reviewed"}), 409

@app.route("/api/reviews/<int:rid>/reply", methods=["POST"])
@token_required
def reply_review(rid):
    d=request.get_json() or {}; content=d.get("content","").strip()
    if not content: return jsonify({"error":"Content required"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("INSERT INTO startuphive_review_replies(review_id,user_id,content) VALUES(%s,%s,%s) RETURNING id",
                (rid,g.uid,content))
    rep_id=cur.fetchone()["id"]; db.commit(); cur.close()
    return jsonify({"id":rep_id}), 201

# ── ASKS ──────────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/asks", methods=["POST"])
@token_required
def add_ask(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    d=request.get_json() or {}; atype=d.get("type","")
    if atype not in ASK_TYPES: return jsonify({"error":"Invalid ask type"}), 400
    cur.execute("INSERT INTO startuphive_asks(startup_id,type,description,urgency) VALUES(%s,%s,%s,%s) RETURNING id",
                (sid,atype,d.get("description",""),d.get("urgency","ongoing") if d.get("urgency") in ["ongoing","this-month","urgent"] else "ongoing"))
    aid=cur.fetchone()["id"]; db.commit(); cur.close(); return jsonify({"id":aid}), 201

@app.route("/api/asks/<int:aid>/respond", methods=["POST"])
@token_required
def respond_ask(aid):
    db=get_db(); cur=db.cursor()
    cur.execute("UPDATE startuphive_asks SET response_count=response_count+1 WHERE id=%s",(aid,))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── METRICS ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/metrics", methods=["POST"])
@token_required
def add_metric(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    d=request.get_json() or {}
    cur.execute("INSERT INTO startuphive_metrics(startup_id,label,value,confidence) VALUES(%s,%s,%s,%s) RETURNING id",
                (sid,d.get("label",""),d.get("value",""),d.get("confidence","claimed")))
    mid=cur.fetchone()["id"]; db.commit(); cur.close(); return jsonify({"id":mid}), 201

@app.route("/api/metrics/<int:mid>", methods=["DELETE"])
@token_required
def delete_metric(mid):
    db=get_db(); cur=db.cursor()
    cur.execute("DELETE FROM startuphive_metrics m USING startuphive_startups s WHERE m.id=%s AND m.startup_id=s.id AND s.user_id=%s",(mid,g.uid))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── TEAM ──────────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/team", methods=["POST"])
@token_required
def add_team(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    d=request.get_json() or {}
    cur.execute("INSERT INTO startuphive_team(startup_id,name,role,bio,avatar_url,linkedin,twitter) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (sid,d.get("name",""),d.get("role",""),d.get("bio",""),d.get("avatar_url",""),d.get("linkedin",""),d.get("twitter","")))
    tid=cur.fetchone()["id"]; db.commit(); cur.close(); return jsonify({"id":tid}), 201

@app.route("/api/team/<int:tid>", methods=["DELETE"])
@token_required
def delete_team(tid):
    db=get_db(); cur=db.cursor()
    cur.execute("DELETE FROM startuphive_team t USING startuphive_startups s WHERE t.id=%s AND t.startup_id=s.id AND s.user_id=%s",(tid,g.uid))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── UPDATES ───────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/updates", methods=["POST"])
@token_required
def post_update(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    d=request.get_json() or {}; title=d.get("title","").strip(); content=d.get("content","").strip()
    if not title or not content: return jsonify({"error":"Title and content required"}), 400
    utype=d.get("type","other") if d.get("type") in UPDATE_TYPES else "other"
    cur.execute("INSERT INTO startuphive_updates(startup_id,user_id,title,content,type,is_pinned) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
                (sid,g.uid,title,content,utype,d.get("is_pinned",False)))
    uid=cur.fetchone()["id"]
    cur.execute("UPDATE startuphive_startups SET last_update_post=NOW(),signal_score=signal_score+3,updated_at=NOW() WHERE id=%s",(sid,))
    db.commit(); cur.close(); log_act("startup_update",g.uid,sid,{"title":title})
    return jsonify({"id":uid}), 201

@app.route("/api/updates/<int:uid>", methods=["DELETE"])
@token_required
def delete_update(uid):
    db=get_db(); cur=db.cursor()
    cur.execute("DELETE FROM startuphive_updates u USING startuphive_startups s WHERE u.id=%s AND u.startup_id=s.id AND s.user_id=%s",(uid,g.uid))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── MESSAGES ──────────────────────────────────────────────────
@app.route("/api/startups/<int:sid>/message", methods=["POST"])
def send_startup_message(sid):
    d=request.get_json() or {}; content=d.get("content","").strip()
    if not content: return jsonify({"error":"Content required"}), 400
    uid=None; auth=request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        try: uid=jwt.decode(auth.split(" ",1)[1],JWT_SECRET,algorithms=[JWT_ALGORITHM])["user_id"]
        except: pass
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id,name FROM startuphive_startups WHERE id=%s AND is_active=TRUE",(sid,))
    s=cur.fetchone()
    if not s: cur.close(); return jsonify({"error":"Not found"}), 404
    sname=d.get("name",""); semail=d.get("email","")
    if uid:
        cur.execute("SELECT name,email FROM startuphive_users WHERE id=%s",(uid,))
        u=cur.fetchone()
        if u: sname=u["name"]; semail=u["email"]
    if not uid and (not sname or not semail): cur.close(); return jsonify({"error":"Name and email required"}), 400
    # Find or create DM conversation between sender and startup owner
    if uid and uid!=s["user_id"]:
        cur.execute("""SELECT c.id FROM startuphive_conversations c
                       JOIN startuphive_conversation_members m1 ON c.id=m1.conversation_id AND m1.user_id=%s
                       JOIN startuphive_conversation_members m2 ON c.id=m2.conversation_id AND m2.user_id=%s""",(uid,s["user_id"]))
        ex=cur.fetchone()
        if ex: conv_id=ex["id"]
        else:
            cur.execute("INSERT INTO startuphive_conversations DEFAULT VALUES RETURNING id"); conv_id=cur.fetchone()["id"]
            cur.execute("INSERT INTO startuphive_conversation_members(conversation_id,user_id) VALUES(%s,%s),(%s,%s)",(conv_id,uid,conv_id,s["user_id"]))
        cur.execute("INSERT INTO startuphive_messages(conversation_id,sender_id,content) VALUES(%s,%s,%s)",(conv_id,uid,content))
        notify(s["user_id"],uid,"startup_message",sid,message=f"New message about {s['name']}")
    cur.execute("UPDATE startuphive_startups SET message_count=message_count+1,signal_score=signal_score+1 WHERE id=%s",(sid,))
    db.commit(); cur.close(); return jsonify({"success":True,"message":"Message delivered"}), 201

@app.route("/api/startups/<int:sid>/messages", methods=["GET"])
@token_required
def get_startup_messages(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    cur.execute("""SELECT m.*,u.avatar_url AS sender_avatar,u.name AS sender_name_db
                   FROM startuphive_messages m LEFT JOIN startuphive_users u ON m.sender_id=u.id
                   WHERE m.conversation_id IN (
                       SELECT DISTINCT cm.conversation_id FROM startuphive_conversation_members cm WHERE cm.user_id=%s
                   ) ORDER BY m.created_at DESC LIMIT 50""",(g.uid,))
    rows=cur.fetchall(); cur.close()
    return jsonify([{"id":r["id"],"content":r["content"],"sender_name":r.get("sender_name_db") or "Guest",
                     "sender_avatar":r.get("sender_avatar") or "","is_read":r["is_read"],
                     "created_at":r["created_at"].isoformat()} for r in rows])

# ── CHATS ─────────────────────────────────────────────────────
@app.route("/api/conversations", methods=["GET"])
@token_required
def get_conversations():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT c.id,u2.id AS partner_id,u2.name AS partner_name,u2.username AS partner_username,
                   u2.avatar_url AS partner_avatar,u2.last_active AS partner_last_active,
                   lm.content AS last_message,lm.created_at AS last_message_at,
                   (SELECT COUNT(*) FROM startuphive_messages WHERE conversation_id=c.id AND sender_id!=%s AND is_read=FALSE) AS unread
                   FROM startuphive_conversations c
                   JOIN startuphive_conversation_members cm1 ON c.id=cm1.conversation_id AND cm1.user_id=%s
                   JOIN startuphive_conversation_members cm2 ON c.id=cm2.conversation_id AND cm2.user_id!=%s
                   JOIN startuphive_users u2 ON cm2.user_id=u2.id
                   LEFT JOIN LATERAL (SELECT content,created_at FROM startuphive_messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) lm ON TRUE
                   ORDER BY lm.created_at DESC NULLS LAST""",(g.uid,g.uid,g.uid))
    rows=cur.fetchall(); cur.close()
    return jsonify([{"id":r["id"],"partner_id":r["partner_id"],"partner_name":r["partner_name"],
                     "partner_username":r["partner_username"],"partner_avatar":r.get("partner_avatar") or "",
                     "partner_last_active":r["partner_last_active"].isoformat() if r.get("partner_last_active") else None,
                     "last_message":r.get("last_message") or "","last_message_at":r["last_message_at"].isoformat() if r.get("last_message_at") else None,
                     "unread":r["unread"]} for r in rows])

@app.route("/api/conversations/start", methods=["POST"])
@token_required
def start_conversation():
    other_id=request.get_json().get("user_id")
    if not other_id or other_id==g.uid: return jsonify({"error":"Invalid"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT c.id FROM startuphive_conversations c
                   JOIN startuphive_conversation_members m1 ON c.id=m1.conversation_id AND m1.user_id=%s
                   JOIN startuphive_conversation_members m2 ON c.id=m2.conversation_id AND m2.user_id=%s""",(g.uid,other_id))
    ex=cur.fetchone()
    if ex: cur.close(); return jsonify({"conversation_id":ex["id"]})
    cur.execute("INSERT INTO startuphive_conversations DEFAULT VALUES RETURNING id"); conv_id=cur.fetchone()["id"]
    cur.execute("INSERT INTO startuphive_conversation_members(conversation_id,user_id) VALUES(%s,%s),(%s,%s)",(conv_id,g.uid,conv_id,other_id))
    db.commit(); cur.close(); return jsonify({"conversation_id":conv_id}), 201

@app.route("/api/conversations/<int:cid>/messages", methods=["GET"])
@token_required
def get_conv_messages(cid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT 1 FROM startuphive_conversation_members WHERE conversation_id=%s AND user_id=%s",(cid,g.uid))
    if not cur.fetchone(): cur.close(); return jsonify({"error":"Forbidden"}), 403
    cur.execute("""SELECT m.*,u.name AS sender_name,u.avatar_url AS sender_avatar
                   FROM startuphive_messages m JOIN startuphive_users u ON m.sender_id=u.id
                   WHERE m.conversation_id=%s ORDER BY m.created_at ASC""",(cid,))
    msgs=cur.fetchall()
    cur.execute("UPDATE startuphive_messages SET is_read=TRUE WHERE conversation_id=%s AND sender_id!=%s",(cid,g.uid))
    cur.execute("UPDATE startuphive_conversation_members SET last_read_at=NOW() WHERE conversation_id=%s AND user_id=%s",(cid,g.uid))
    db.commit(); cur.close()
    return jsonify([{"id":m["id"],"content":m["content"],"sender_id":m["sender_id"],
                     "sender_name":m["sender_name"],"sender_avatar":m.get("sender_avatar") or "",
                     "is_read":m["is_read"],"mine":m["sender_id"]==g.uid,
                     "created_at":m["created_at"].isoformat()} for m in msgs])

@app.route("/api/conversations/<int:cid>/messages", methods=["POST"])
@token_required
def send_message(cid):
    content=request.get_json().get("content","").strip()
    if not content: return jsonify({"error":"Content required"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT 1 FROM startuphive_conversation_members WHERE conversation_id=%s AND user_id=%s",(cid,g.uid))
    if not cur.fetchone(): cur.close(); return jsonify({"error":"Forbidden"}), 403
    cur.execute("INSERT INTO startuphive_messages(conversation_id,sender_id,content) VALUES(%s,%s,%s) RETURNING id,created_at",(cid,g.uid,content))
    row=cur.fetchone()
    cur.execute("UPDATE startuphive_conversations SET updated_at=NOW() WHERE id=%s",(cid,))
    db.commit(); cur.close()
    return jsonify({"id":row["id"],"content":content,"sender_id":g.uid,"mine":True,"is_read":False,"created_at":row["created_at"].isoformat()}), 201

@app.route("/api/conversations/<int:cid>/check", methods=["GET"])
@token_required
def check_messages(cid):
    db=get_db(); cur=db.cursor()
    after=request.args.get("after",0,type=int)
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_messages WHERE conversation_id=%s",(cid,))
    total=cur.fetchone()["c"]
    cur.execute("SELECT last_active FROM startuphive_users u JOIN startuphive_conversation_members cm ON cm.user_id=u.id WHERE cm.conversation_id=%s AND cm.user_id!=%s",(cid,g.uid))
    partner=cur.fetchone(); cur.close()
    return jsonify({"has_new":total>after,"total":total,"partner_last_active":partner["last_active"].isoformat() if partner else None})

# ── COMMUNITY POSTS ───────────────────────────────────────────
@app.route("/api/community", methods=["GET"])
@optional_token
def community_posts():
    community=request.args.get("community","s/general"); sort=request.args.get("sort","hot")
    page=max(1,request.args.get("page",1,type=int)); per_page=20
    db=get_db(); cur=db.cursor()
    where="WHERE cp.community=%s" if community!="all" else ""
    params=[community] if community!="all" else []
    order={"hot":"cp.upvote_count-cp.downvote_count DESC,cp.created_at DESC","new":"cp.created_at DESC","top":"cp.upvote_count DESC"}.get(sort,"cp.created_at DESC")
    offset=(page-1)*per_page
    cur.execute(f"""SELECT cp.*,u.name AS author_name,u.username AS author_username,u.avatar_url AS author_avatar
                    FROM startuphive_community_posts cp JOIN startuphive_users u ON cp.user_id=u.id
                    {where} ORDER BY {order} LIMIT %s OFFSET %s""",params+[per_page,offset])
    rows=cur.fetchall()
    cur.execute(f"SELECT COUNT(*) AS t FROM startuphive_community_posts cp {where}",params)
    total=cur.fetchone()["t"]
    user_votes={}
    if g.uid and rows:
        ids=[r["id"] for r in rows]
        cur.execute("SELECT post_id,vote_type FROM startuphive_community_votes WHERE user_id=%s AND post_id=ANY(%s)",(g.uid,ids))
        user_votes={r["post_id"]:r["vote_type"] for r in cur.fetchall()}
    cur.close()
    return jsonify({"posts":[{"id":r["id"],"community":r["community"],"title":r.get("title") or "",
                               "content":r.get("content") or "","media_url":r.get("media_url") or "",
                               "media_type":r["media_type"],"upvote_count":r["upvote_count"],"downvote_count":r["downvote_count"],
                               "comment_count":r["comment_count"],"is_pinned":r["is_pinned"],
                               "author_name":r["author_name"],"author_username":r["author_username"],
                               "author_avatar":r.get("author_avatar") or "","my_vote":user_votes.get(r["id"]),
                               "created_at":r["created_at"].isoformat()} for r in rows],
                    "total":total,"pages":max(1,-(-total//per_page))})

@app.route("/api/community", methods=["POST"])
@token_required
def create_post():
    d=request.get_json() or {}
    community=d.get("community","s/general")
    if community not in COMMUNITIES: return jsonify({"error":"Invalid community"}), 400
    content=d.get("content","").strip()
    if not content and not d.get("media_url"): return jsonify({"error":"Content required"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("INSERT INTO startuphive_community_posts(user_id,community,title,content,media_url,media_type) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
                (g.uid,community,d.get("title",""),content,d.get("media_url",""),d.get("media_type","text")))
    pid=cur.fetchone()["id"]; db.commit(); cur.close()
    log_act("community_post",g.uid,meta={"community":community})
    return jsonify({"id":pid}), 201

@app.route("/api/community/<int:pid>/vote", methods=["POST"])
@token_required
def vote_post(pid):
    vtype=request.get_json().get("vote_type","")
    if vtype not in ("up","down"): return jsonify({"error":"Invalid vote"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT vote_type FROM startuphive_community_votes WHERE post_id=%s AND user_id=%s",(pid,g.uid))
    existing=cur.fetchone()
    if existing:
        if existing["vote_type"]==vtype:
            cur.execute("DELETE FROM startuphive_community_votes WHERE post_id=%s AND user_id=%s",(pid,g.uid))
            cur.execute(f"UPDATE startuphive_community_posts SET {vtype}vote_count=GREATEST(0,{vtype}vote_count-1) WHERE id=%s",(pid,))
            db.commit(); cur.close(); return jsonify({"vote_type":None})
        else:
            cur.execute("UPDATE startuphive_community_votes SET vote_type=%s WHERE post_id=%s AND user_id=%s",(vtype,pid,g.uid))
            old={"up":"down","down":"up"}[vtype]
            cur.execute(f"UPDATE startuphive_community_posts SET {vtype}vote_count={vtype}vote_count+1,{old}vote_count=GREATEST(0,{old}vote_count-1) WHERE id=%s",(pid,))
    else:
        cur.execute("INSERT INTO startuphive_community_votes(post_id,user_id,vote_type) VALUES(%s,%s,%s)",(pid,g.uid,vtype))
        cur.execute(f"UPDATE startuphive_community_posts SET {vtype}vote_count={vtype}vote_count+1 WHERE id=%s",(pid,))
    db.commit(); cur.close(); return jsonify({"vote_type":vtype})

@app.route("/api/community/<int:pid>/comments", methods=["GET"])
def get_comments(pid):
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT cc.*,u.name AS author_name,u.username AS author_username,u.avatar_url AS author_avatar
                   FROM startuphive_community_comments cc JOIN startuphive_users u ON cc.user_id=u.id
                   WHERE cc.post_id=%s AND cc.parent_id IS NULL ORDER BY cc.created_at""",(pid,))
    top=cur.fetchall()
    cur.execute("""SELECT cc.*,u.name AS author_name,u.username AS author_username,u.avatar_url AS author_avatar
                   FROM startuphive_community_comments cc JOIN startuphive_users u ON cc.user_id=u.id
                   WHERE cc.post_id=%s AND cc.parent_id IS NOT NULL ORDER BY cc.created_at""",(pid,))
    replies_raw=cur.fetchall(); replies_map={}
    for r in replies_raw: replies_map.setdefault(r["parent_id"],[]).append(r)
    cur.close()
    def fmt(c):
        return {"id":c["id"],"content":c["content"],"like_count":c["like_count"],
                "author_name":c["author_name"],"author_username":c["author_username"],
                "author_avatar":c.get("author_avatar") or "","created_at":c["created_at"].isoformat(),
                "replies":[fmt(r) for r in replies_map.get(c["id"],[])]}
    return jsonify([fmt(c) for c in top])

@app.route("/api/community/<int:pid>/comments", methods=["POST"])
@token_required
def post_comment(pid):
    d=request.get_json() or {}; content=d.get("content","").strip()
    if not content: return jsonify({"error":"Content required"}), 400
    db=get_db(); cur=db.cursor()
    cur.execute("INSERT INTO startuphive_community_comments(post_id,user_id,parent_id,content) VALUES(%s,%s,%s,%s) RETURNING id",
                (pid,g.uid,d.get("parent_id"),content))
    cid=cur.fetchone()["id"]
    cur.execute("UPDATE startuphive_community_posts SET comment_count=comment_count+1 WHERE id=%s",(pid,))
    db.commit(); cur.close(); return jsonify({"id":cid}), 201

# ── NOTIFICATIONS ─────────────────────────────────────────────
@app.route("/api/notifications", methods=["GET"])
@token_required
def get_notifications():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT n.*,u.name AS actor_name,u.avatar_url AS actor_avatar
                   FROM startuphive_notifications n LEFT JOIN startuphive_users u ON n.actor_id=u.id
                   WHERE n.user_id=%s ORDER BY n.created_at DESC LIMIT 50""",(g.uid,))
    rows=cur.fetchall()
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_notifications WHERE user_id=%s AND is_read=FALSE",(g.uid,))
    unread=cur.fetchone()["c"]; cur.close()
    return jsonify({"notifications":[{"id":r["id"],"type":r["type"],"message":r.get("message") or "",
                     "link":r.get("link") or "","is_read":r["is_read"],"actor_name":r.get("actor_name") or "",
                     "actor_avatar":r.get("actor_avatar") or "","created_at":r["created_at"].isoformat()} for r in rows],
                    "unread_count":unread})

@app.route("/api/notifications/read", methods=["PUT"])
@token_required
def mark_notif_read():
    nid=request.get_json().get("id")
    db=get_db(); cur=db.cursor()
    if nid: cur.execute("UPDATE startuphive_notifications SET is_read=TRUE WHERE id=%s AND user_id=%s",(nid,g.uid))
    else: cur.execute("UPDATE startuphive_notifications SET is_read=TRUE WHERE user_id=%s",(g.uid,))
    db.commit(); cur.close(); return jsonify({"success":True})

# ── DASHBOARD ─────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
@token_required
def dashboard():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT id,name,slug,logo_url,stage,status,is_active,is_featured,
                          view_count,upvote_count,bookmark_count,message_count,signal_score,
                          verification_level,created_at,last_update_post
                   FROM startuphive_startups WHERE user_id=%s ORDER BY created_at DESC""",(g.uid,))
    startups=cur.fetchall()
    ids=[s["id"] for s in startups]; unread=0
    if ids:
        cur.execute("SELECT COUNT(*) AS c FROM startuphive_messages m JOIN startuphive_conversation_members cm ON m.conversation_id=cm.conversation_id WHERE cm.user_id=%s AND m.sender_id!=%s AND m.is_read=FALSE",(g.uid,g.uid))
        unread=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_notifications WHERE user_id=%s AND is_read=FALSE",(g.uid,))
    unread_notifs=cur.fetchone()["c"]
    cur.close()
    return jsonify({"startups":[{"id":s["id"],"name":s["name"],"slug":s["slug"],"logo_url":s.get("logo_url") or "",
                     "stage":s["stage"],"status":s["status"],"is_active":s["is_active"],"is_featured":s["is_featured"],
                     "view_count":s["view_count"],"upvote_count":s["upvote_count"],"bookmark_count":s["bookmark_count"],
                     "message_count":s["message_count"],"signal_score":s["signal_score"],
                     "verification_level":s["verification_level"],"created_at":s["created_at"].isoformat(),
                     "last_update_post":s["last_update_post"].isoformat() if s["last_update_post"] else None} for s in startups],
                    "totals":{"startup_count":len(startups),
                              "total_views":sum(s["view_count"] for s in startups),
                              "total_upvotes":sum(s["upvote_count"] for s in startups),
                              "total_bookmarks":sum(s["bookmark_count"] for s in startups),
                              "total_messages":sum(s["message_count"] for s in startups),
                              "unread_messages":unread,"unread_notifications":unread_notifs}})

# ── STARTUP HEALTH CHECK ──────────────────────────────────────
@app.route("/api/startups/<int:sid>/health", methods=["GET"])
@token_required
def startup_health(sid):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT user_id FROM startuphive_startups WHERE id=%s",(sid,)); row=cur.fetchone()
    if not row or row["user_id"]!=g.uid: cur.close(); return jsonify({"error":"Forbidden"}), 403
    cur.execute("SELECT * FROM startuphive_startups WHERE id=%s",(sid,)); s=cur.fetchone()
    cur.execute("SELECT * FROM startuphive_startup_content WHERE startup_id=%s",(sid,)); c=cur.fetchone()
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_metrics WHERE startup_id=%s AND is_current=TRUE",(sid,)); metrics_count=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_team WHERE startup_id=%s",(sid,)); team_count=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_updates WHERE startup_id=%s",(sid,)); updates_count=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_asks WHERE startup_id=%s AND is_active=TRUE",(sid,)); asks_count=cur.fetchone()["c"]
    # Platform averages for comparison
    cur.execute("SELECT AVG(upvote_count) AS avg_uv,AVG(view_count) AS avg_vw FROM startuphive_startups WHERE is_active=TRUE"); platform=cur.fetchone()
    cur.close()
    score=0; advice=[]; strengths=[]; improvements=[]
    # Profile completeness
    if s.get("logo_url"): score+=10; strengths.append("Logo uploaded — strong first impression")
    else: improvements.append("Upload a logo — profiles with logos get 3x more views")
    if s.get("tagline"): score+=10
    if c and c.get("about_problem"): score+=15; strengths.append("Problem clearly defined")
    else: improvements.append("Define your problem statement — investors look for this first")
    if c and c.get("about_solution"): score+=15
    if c and c.get("about_why_now"): score+=10
    if metrics_count>0: score+=15; strengths.append(f"{metrics_count} metric(s) added — traction signals attract attention")
    else: improvements.append("Add at least one traction metric — even pre-revenue signals matter")
    if team_count>0: score+=10
    else: improvements.append("Add team members — solo founders convert less")
    if updates_count>0: score+=10; strengths.append("Posted updates — active profiles rank higher")
    else: improvements.append("Post at least one update — signal you're building")
    if asks_count>0: score+=10
    else: improvements.append("Add what you need — this surfaces you to the right people")
    if s.get("contact_methods") and sj(s.get("contact_methods")): score+=10; strengths.append("Contact methods visible — zero friction for outreach")
    else: improvements.append("Add contact methods — make yourself reachable")
    # Comparative advice
    avg_uv=float(platform["avg_uv"] or 0); avg_vw=float(platform["avg_vw"] or 0)
    if s["upvote_count"]>avg_uv: advice.append(f"Your upvotes ({s['upvote_count']}) are above platform average ({avg_uv:.0f}) — strong community signal")
    elif s["upvote_count"]<avg_uv*0.3: advice.append("Upvotes below average — share your listing on social media and community channels")
    if s["view_count"]>avg_vw: advice.append("High view count — consider adding a demo video to convert visitors")
    days_since_update=99
    if s.get("updated_at"):
        days_since_update=(datetime.datetime.utcnow()-s["updated_at"].replace(tzinfo=None)).days
    if days_since_update>30: advice.append(f"Profile last updated {days_since_update} days ago — fresh profiles appear higher in discovery. Post an update now.")
    elif days_since_update<7: strengths.append("Recently updated — your profile is fresh and active")
    return jsonify({"score":min(100,score),"grade":"A" if score>=85 else "B" if score>=70 else "C" if score>=50 else "D",
                    "strengths":strengths,"improvements":improvements,"advice":advice,
                    "stats":{"upvotes":s["upvote_count"],"views":s["view_count"],"signals":s["signal_score"],
                             "metrics":metrics_count,"team":team_count,"updates":updates_count}})

# ── SEARCH ────────────────────────────────────────────────────
@app.route("/api/search", methods=["GET"])
def search():
    q=request.args.get("q","").strip(); tab=request.args.get("tab","startups")
    if len(q)<2: return jsonify({"startups":[],"users":[],"posts":[]})
    db=get_db(); cur=db.cursor(); lq=f"%{q}%"
    if tab in ("startups","all"):
        cur.execute("SELECT id,name,slug,tagline,logo_url,categories,stage,upvote_count,verification_level FROM startuphive_startups WHERE is_active=TRUE AND (name ILIKE %s OR tagline ILIKE %s OR %s=ANY(categories)) ORDER BY upvote_count DESC LIMIT 12",(lq,lq,q))
        startups=cur.fetchall()
    else: startups=[]
    if tab in ("users","all"):
        cur.execute("SELECT id,name,username,avatar_url,headline,is_verified FROM startuphive_users WHERE name ILIKE %s OR username ILIKE %s LIMIT 8",(lq,lq))
        users=cur.fetchall()
    else: users=[]
    if tab in ("posts","all"):
        cur.execute("SELECT cp.id,cp.community,cp.title,cp.content,cp.upvote_count,u.name AS author_name FROM startuphive_community_posts cp JOIN startuphive_users u ON cp.user_id=u.id WHERE cp.title ILIKE %s OR cp.content ILIKE %s ORDER BY cp.upvote_count DESC LIMIT 8",(lq,lq))
        posts=cur.fetchall()
    else: posts=[]
    cur.close()
    return jsonify({"startups":[{"id":s["id"],"name":s["name"],"slug":s["slug"],"tagline":s.get("tagline") or "",
                    "logo_url":s.get("logo_url") or "","categories":sa(s.get("categories")),"stage":s["stage"],
                    "upvote_count":s["upvote_count"],"level":s["verification_level"]} for s in startups],
                    "users":[{"id":u["id"],"name":u["name"],"username":u["username"],"avatar_url":u.get("avatar_url") or "",
                    "headline":u.get("headline") or "","is_verified":u["is_verified"]} for u in users],
                    "posts":[{"id":p["id"],"community":p["community"],"title":p.get("title") or "","content":(p.get("content") or "")[:150],
                    "upvote_count":p["upvote_count"],"author_name":p["author_name"]} for p in posts]})

# ── STATS ─────────────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def platform_stats():
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE is_active=TRUE"); ts=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_users"); tu=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE is_active=TRUE AND created_at>=NOW()-INTERVAL '7 days'"); nw=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_upvotes WHERE created_at>=CURRENT_DATE"); ud=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_signals WHERE created_at>=NOW()-INTERVAL '7 days'"); sw=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_startups WHERE verification_level IN('verified','audited') AND is_active=TRUE"); vc=cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM startuphive_community_posts WHERE created_at>=NOW()-INTERVAL '24 hours'"); cp=cur.fetchone()["c"]
    cur.close()
    return jsonify({"total_startups":ts,"total_users":tu,"new_this_week":nw,"upvotes_today":ud,
                    "signals_this_week":sw,"verified_startups":vc,"community_posts_today":cp})

# ── ACTIVITY FEED ─────────────────────────────────────────────
@app.route("/api/activity", methods=["GET"])
def activity_feed():
    db=get_db(); cur=db.cursor()
    cur.execute("""SELECT a.type,a.meta,a.created_at,u.name AS user_name,u.username AS user_username,u.avatar_url AS user_avatar,
                   s.name AS startup_name,s.slug AS startup_slug,s.logo_url AS startup_logo,s.categories AS startup_categories
                   FROM startuphive_activity a LEFT JOIN startuphive_users u ON a.user_id=u.id
                   LEFT JOIN startuphive_startups s ON a.startup_id=s.id
                   WHERE a.type IN('startup_listed','startup_update','upvote','user_joined','community_post')
                   ORDER BY a.created_at DESC LIMIT 25""")
    rows=cur.fetchall(); cur.close()
    return jsonify([{"type":r["type"],"meta":sj(r["meta"]),"user_name":r.get("user_name") or "",
                     "user_username":r.get("user_username") or "","user_avatar":r.get("user_avatar") or "",
                     "startup_name":r.get("startup_name") or "","startup_slug":r.get("startup_slug") or "",
                     "startup_logo":r.get("startup_logo") or "","startup_categories":sa(r.get("startup_categories")),
                     "created_at":r["created_at"].isoformat()} for r in rows])

# ── PUBLIC PROFILE ────────────────────────────────────────────
@app.route("/api/users/<username>", methods=["GET"])
def get_user(username):
    db=get_db(); cur=db.cursor()
    cur.execute("SELECT id,name,username,avatar_url,cover_url,bio,headline,website,twitter,linkedin,github,is_verified,reputation,last_active,created_at FROM startuphive_users WHERE username=%s",(username,))
    u=cur.fetchone()
    if not u: cur.close(); return jsonify({"error":"Not found"}), 404
    cur.execute("SELECT id,name,slug,tagline,logo_url,categories,stage,status,upvote_count,view_count,is_active,created_at FROM startuphive_startups WHERE user_id=%s AND is_active=TRUE ORDER BY created_at DESC",(u["id"],))
    startups=cur.fetchall(); cur.close()
    return jsonify({**fmt_user(u),"startups":[fmt_startup(s) for s in startups]})

# ── PING ──────────────────────────────────────────────────────
@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"status":"alive","service":"startuphive","ts":datetime.datetime.utcnow().isoformat()})

@app.route("/")
def root():
    return jsonify({"service":"StartupHive API","version":"3.0.0","status":"running"})

# ── BOOT ──────────────────────────────────────────────────────
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)