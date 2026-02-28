# ═══════════════════════════════════════════════════════════════
# MODULES.PY — Treℵds Platform Backend Logic
# ═══════════════════════════════════════════════════════════════

import psycopg2
import psycopg2.pool
import bcrypt
import uuid
import json
import secrets
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
import Appmodulator as A

# ═══════════════════════════════════════════════════════════════
# CONNECTION POOL
# ═══════════════════════════════════════════════════════════════
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=20,
            host=A.DB_HOST, database=A.DB_NAME,
            user=A.DB_USER, password=A.DB_PASSWORD, port=A.DB_PORT
        )
    return _pool

def get_conn():
    return get_pool().getconn()

def release_conn(conn):
    get_pool().putconn(conn)

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def gen_key():
    return str(uuid.uuid4()).replace("-", "")

def gen_token():
    return secrets.token_urlsafe(48)

def hash_password(pw):
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(pw, hashed):
    return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))

def time_ago(timestamp):
    if not timestamp:
        return ""
    now  = datetime.utcnow()
    diff = now - timestamp
    s    = int(diff.total_seconds())
    if s < 60:       return "Just now"
    if s < 3600:     return f"{s // 60}m ago"
    if s < 86400:    return f"{s // 3600}h ago"
    if s < 604800:   return f"{s // 86400}d ago"
    return timestamp.strftime("%b %d, %Y")

def get_user_by_key(user_key):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM user_auth WHERE user_key = %s", (user_key,))
        return cur.fetchone()
    finally:
        release_conn(conn)

def get_user_by_email(email):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM user_auth WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        release_conn(conn)

def get_user_from_token(token):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.* FROM user_auth u
            JOIN sessions s ON s.user_key = u.user_key
            WHERE s.token = %s AND s.expires_at > NOW()
        """, (token,))
        return cur.fetchone()
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# CREATE TABLES
# ═══════════════════════════════════════════════════════════════
def create_table():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""

            -- USER AUTH
            CREATE TABLE IF NOT EXISTS user_auth (
                id                        SERIAL PRIMARY KEY,
                user_key                  VARCHAR(64) UNIQUE NOT NULL,
                full_name                 VARCHAR(100) NOT NULL,
                username                  VARCHAR(50) UNIQUE NOT NULL,
                email                     VARCHAR(255) UNIQUE NOT NULL,
                password                  VARCHAR(255) NOT NULL,
                university                VARCHAR(200) DEFAULT '',
                department                VARCHAR(200) DEFAULT '',
                academic_level            VARCHAR(100) DEFAULT '',
                created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                profilepicurl             TEXT DEFAULT '',
                biodescription            TEXT DEFAULT '',
                account_level             VARCHAR(20) DEFAULT 'normal',
                numberoffollowers         INTEGER DEFAULT 0,
                numberoffollowing         INTEGER DEFAULT 0,
                numberoflikes             INTEGER DEFAULT 0,
                numberofposts             INTEGER DEFAULT 0,
                is_private                BOOLEAN DEFAULT FALSE,
                show_activity_status      BOOLEAN DEFAULT TRUE,
                post_visibility           VARCHAR(20) DEFAULT 'public',
                research_visibility       VARCHAR(20) DEFAULT 'public',
                message_privacy           VARCHAR(20) DEFAULT 'everyone',
                tag_privacy               VARCHAR(20) DEFAULT 'everyone',
                followers_list_visibility VARCHAR(20) DEFAULT 'everyone',
                read_receipts             BOOLEAN DEFAULT TRUE,
                typing_indicators         BOOLEAN DEFAULT TRUE,
                message_requests_filter   VARCHAR(20) DEFAULT 'everyone',
                notif_likes               BOOLEAN DEFAULT TRUE,
                notif_comments            BOOLEAN DEFAULT TRUE,
                notif_follows             BOOLEAN DEFAULT TRUE,
                notif_mentions            BOOLEAN DEFAULT TRUE,
                notif_messages            BOOLEAN DEFAULT TRUE,
                notif_events              BOOLEAN DEFAULT TRUE,
                notif_bounties            BOOLEAN DEFAULT TRUE,
                notif_email               BOOLEAN DEFAULT TRUE,
                notif_push                BOOLEAN DEFAULT TRUE,
                theme                     VARCHAR(10) DEFAULT 'dark',
                font_size                 VARCHAR(10) DEFAULT 'medium',
                compact_mode              BOOLEAN DEFAULT FALSE,
                two_factor_enabled        BOOLEAN DEFAULT FALSE,
                last_password_change      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deactivated            BOOLEAN DEFAULT FALSE,
                last_seen                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- SESSIONS
            CREATE TABLE IF NOT EXISTS sessions (
                id         SERIAL PRIMARY KEY,
                session_key VARCHAR(64) UNIQUE NOT NULL,
                user_key   VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                token      VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );

            -- POSTS
            CREATE TABLE IF NOT EXISTS posts (
                id             SERIAL PRIMARY KEY,
                post_key       VARCHAR(64) UNIQUE NOT NULL,
                user_key       VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                post_type      VARCHAR(20) NOT NULL,
                content        TEXT DEFAULT '',
                media_url      TEXT DEFAULT '',
                media_type     VARCHAR(20) DEFAULT '',
                visibility     VARCHAR(20) DEFAULT 'public',
                allow_comments BOOLEAN DEFAULT TRUE,
                show_in_feed   BOOLEAN DEFAULT TRUE,
                like_count     INTEGER DEFAULT 0,
                comment_count  INTEGER DEFAULT 0,
                share_count    INTEGER DEFAULT 0,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- POST EXTRAS (poll, event, bounty, research, job, product, collab, ad)
            CREATE TABLE IF NOT EXISTS post_extras (
                id       SERIAL PRIMARY KEY,
                post_key VARCHAR(64) UNIQUE NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                data     JSONB NOT NULL DEFAULT '{}'
            );

            -- POLL VOTES
            CREATE TABLE IF NOT EXISTS poll_votes (
                id           SERIAL PRIMARY KEY,
                vote_key     VARCHAR(64) UNIQUE NOT NULL,
                post_key     VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key     VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                option_index INTEGER NOT NULL,
                voted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_key, user_key)
            );

            -- EVENT RSVPS
            CREATE TABLE IF NOT EXISTS event_rsvps (
                id          SERIAL PRIMARY KEY,
                rsvp_key    VARCHAR(64) UNIQUE NOT NULL,
                post_key    VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key    VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                rsvp_status VARCHAR(20) NOT NULL,
                rsvp_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_key, user_key)
            );

            -- BOUNTY APPLICATIONS
            CREATE TABLE IF NOT EXISTS bounty_applications (
                id       SERIAL PRIMARY KEY,
                app_key  VARCHAR(64) UNIQUE NOT NULL,
                post_key VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                message  TEXT DEFAULT '',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_key, user_key)
            );

            -- LIKES
            CREATE TABLE IF NOT EXISTS likes (
                id       SERIAL PRIMARY KEY,
                like_key VARCHAR(64) UNIQUE NOT NULL,
                post_key VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_key, user_key)
            );

            -- COMMENTS
            CREATE TABLE IF NOT EXISTS comments (
                id           SERIAL PRIMARY KEY,
                comment_key  VARCHAR(64) UNIQUE NOT NULL,
                post_key     VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key     VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                content      TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- BOOKMARKS
            CREATE TABLE IF NOT EXISTS bookmarks (
                id           SERIAL PRIMARY KEY,
                bookmark_key VARCHAR(64) UNIQUE NOT NULL,
                post_key     VARCHAR(64) NOT NULL REFERENCES posts(post_key) ON DELETE CASCADE,
                user_key     VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                saved_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_key, user_key)
            );

            -- FOLLOWS
            CREATE TABLE IF NOT EXISTS follows (
                id            SERIAL PRIMARY KEY,
                follow_key    VARCHAR(64) UNIQUE NOT NULL,
                follower_key  VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                following_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                followed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(follower_key, following_key)
            );

            -- BLOCKS
            CREATE TABLE IF NOT EXISTS blocks (
                id           SERIAL PRIMARY KEY,
                block_key    VARCHAR(64) UNIQUE NOT NULL,
                blocker_key  VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                blocked_key  VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                blocked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(blocker_key, blocked_key)
            );

            -- NOTIFICATIONS
            CREATE TABLE IF NOT EXISTS notifications (
                id             SERIAL PRIMARY KEY,
                notif_key      VARCHAR(64) UNIQUE NOT NULL,
                recipient_key  VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                sender_key     VARCHAR(64) REFERENCES user_auth(user_key) ON DELETE SET NULL,
                notif_type     VARCHAR(30) NOT NULL,
                post_key       VARCHAR(64) DEFAULT '',
                message        TEXT DEFAULT '',
                is_read        BOOLEAN DEFAULT FALSE,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- CONVERSATIONS
            CREATE TABLE IF NOT EXISTS conversations (
                id         SERIAL PRIMARY KEY,
                convo_key  VARCHAR(64) UNIQUE NOT NULL,
                user_a_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                user_b_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_key, user_b_key)
            );

            -- MESSAGES
            CREATE TABLE IF NOT EXISTS messages (
                id           SERIAL PRIMARY KEY,
                msg_key      VARCHAR(64) UNIQUE NOT NULL,
                convo_key    VARCHAR(64) NOT NULL REFERENCES conversations(convo_key) ON DELETE CASCADE,
                sender_key   VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                content      TEXT DEFAULT '',
                media_url    TEXT DEFAULT '',
                is_read      BOOLEAN DEFAULT FALSE,
                reply_to_key VARCHAR(64) DEFAULT '',
                sent_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- GLOBAL CHAT
            CREATE TABLE IF NOT EXISTS global_chat (
                id       SERIAL PRIMARY KEY,
                msg_key  VARCHAR(64) UNIQUE NOT NULL,
                user_key VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                content  TEXT NOT NULL,
                sent_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- SEARCH PAIRS (for clustering algorithm)
            CREATE TABLE IF NOT EXISTS search_pairs (
                id            SERIAL PRIMARY KEY,
                pair_key      VARCHAR(64) UNIQUE NOT NULL,
                query         TEXT NOT NULL,
                selected      TEXT NOT NULL,
                weight        FLOAT DEFAULT 1.0,
                last_searched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(query, selected)
            );

            -- ADS
            CREATE TABLE IF NOT EXISTS ads (
                id         SERIAL PRIMARY KEY,
                ad_key     VARCHAR(64) UNIQUE NOT NULL,
                user_key   VARCHAR(64) NOT NULL REFERENCES user_auth(user_key) ON DELETE CASCADE,
                title      TEXT NOT NULL,
                media_url  TEXT DEFAULT '',
                body_text  TEXT DEFAULT '',
                cta        TEXT DEFAULT '',
                link       TEXT DEFAULT '',
                active     BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

        """)
        conn.commit()
        cur.close()
        print("[TrendsDB] All tables created/verified ✓")
    except Exception as e:
        conn.rollback()
        print(f"[TrendsDB] Error: {e}")
        raise
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════
def verify_signup_data(x):
    conn = get_conn()
    try:
        cur = conn.cursor()
        email    = x['email'].strip().lower()
        username = x['username'].strip().lower()
        cur.execute("SELECT 1 FROM user_auth WHERE email = %s",    (email,))
        email_exists = cur.fetchone()
        cur.execute("SELECT 1 FROM user_auth WHERE username = %s", (username,))
        username_exists = cur.fetchone()
        cur.close()
        if email_exists and username_exists:
            return {'status': 400, 'error': 'both'}
        if email_exists:
            return {'status': 400, 'error': 'email'}
        if username_exists:
            return {'status': 400, 'error': 'username'}
        return {'status': 200}
    finally:
        release_conn(conn)

def insert_user(x):
    conn = get_conn()
    try:
        cur      = conn.cursor()
        user_key = gen_key()
        hashed   = hash_password(x['password'])
        cur.execute("""
            INSERT INTO user_auth
              (user_key, full_name, username, email, password,
               university, department, academic_level, biodescription)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_key,
            x['full_name'].strip(),
            x['username'].strip().lower(),
            x['email'].strip().lower(),
            hashed,
            x.get('university', ''),
            x.get('department', ''),
            x.get('academic_level', ''),
            A.defaultbiodescription
        ))
        conn.commit()
        cur.close()
        return user_key
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def verify_signin_data(x):
    user = get_user_by_email(x['email'].strip().lower())
    if not user:
        return {'status': 400, 'error': 'credentials'}
    if user['is_deactivated']:
        return {'status': 400, 'error': 'deactivated'}
    if not check_password(x['password'], user['password']):
        return {'status': 400, 'error': 'credentials'}
    return {'status': 200, 'user_key': user['user_key']}

def create_session(user_key):
    conn = get_conn()
    try:
        cur        = conn.cursor()
        token      = gen_token()
        session_key = gen_key()
        expires_at = datetime.utcnow() + timedelta(days=A.SESSION_DURATION_DAYS)
        cur.execute("""
            INSERT INTO sessions (session_key, user_key, token, expires_at)
            VALUES (%s, %s, %s, %s)
        """, (session_key, user_key, token, expires_at))
        conn.commit()
        cur.close()
        return token
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def validate_session(token):
    if not token:
        return None
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT user_key FROM sessions
            WHERE token = %s AND expires_at > NOW()
        """, (token,))
        row = cur.fetchone()
        cur.close()
        return row['user_key'] if row else None
    finally:
        release_conn(conn)

def logout(token):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
        conn.commit()
        cur.close()
        return {'status': 200}
    finally:
        release_conn(conn)

def update_last_seen(user_key):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE user_auth SET last_seen = NOW() WHERE user_key = %s", (user_key,))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)

def deactivate_account(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    user = get_user_by_key(user_key)
    if not check_password(x.get('password', ''), user['password']):
        return {'status': 400, 'message': A.Incorrectpasswordmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE user_auth SET is_deactivated = TRUE WHERE user_key = %s", (user_key,))
        cur.execute("DELETE FROM sessions WHERE user_key = %s", (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Accountdeactivatesuccessmsg}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def delete_account(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    user = get_user_by_key(user_key)
    if not check_password(x.get('password', ''), user['password']):
        return {'status': 400, 'message': A.Incorrectpasswordmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_auth WHERE user_key = %s", (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Accountdeletesuccessmsg}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# PROFILE HTML BUILDERS
# ═══════════════════════════════════════════════════════════════
def drawerprofilenav(user):
    name       = user['full_name']
    university = user.get('university', '')
    department = user.get('department', '')
    bio        = user.get('biodescription') or A.defaultbiodescription
    pic        = user.get('profilepicurl') or A.defaultavatarurl
    img_style  = "display:block;" if pic else "display:none;"
    initials   = ''.join([p[0].upper() for p in name.split()[:2]])
    return f'''<pib><img style="{img_style}" src="{pic}">{initials}</pib><div class="dr-info"><un>{name}</un><lr>{university} &bull; {department}</lr><aside><marquee>{bio}</marquee></aside></div>'''

def profileinfo(user):
    name       = user['full_name']
    username   = user['username']
    department = user.get('department', '')
    level      = user.get('academic_level', '')
    university = user.get('university', '')
    tick       = ' ✓' if user.get('account_level') == 'premium' else ''
    return f'''<div class="name">{name}{tick}</div>
<div class="handle">@{username}</div>
<div class="bio">{department} &bull; {level} &bull; {university}</div>'''

def profilestats(user):
    followers = user.get('numberoffollowers', 0)
    following = user.get('numberoffollowing', 0)
    likes     = user.get('numberoflikes', 0)
    posts     = user.get('numberofposts', 0)
    def fmt(n):
        if n >= 1000000: return f"{n/1000000:.1f}M"
        if n >= 1000:    return f"{n/1000:.1f}K"
        return str(n)
    return f'''<div onclick="openUserModal('following')" style="cursor:pointer;"><div class="stat-num">{fmt(following)}</div><div class="stat-label">Following</div></div>
<div onclick="openUserModal('followers')" style="cursor:pointer;"><div class="stat-num">{fmt(followers)}</div><div class="stat-label">Followers</div></div>
<div><div class="stat-num">{fmt(likes)}</div><div class="stat-label">Likes</div></div>
<div><div class="stat-num">{fmt(posts)}</div><div class="stat-label">Posts</div></div>'''

def get_avatar_html(user):
    pic = user.get('profilepicurl') or A.defaultavatarurl
    return pic

def settings_payload(user):
    return {
        'setProfileName':   user['full_name'],
        'setProfileHandle': f"@{user['username']} &bull; {user.get('department','')} &bull; {user.get('university','')}",
        'setEmail':         user['email'],
        'setUsername':      f"@{user['username']}",
        'setBio':           user.get('biodescription') or A.defaultbiodescription,
        'setUniversity':    user.get('university', ''),
        'setDepartment':    user.get('department', ''),
        'setProfilePic':    user.get('profilepicurl') or A.defaultavatarurl,
    }


# ═══════════════════════════════════════════════════════════════
# PROFILE DATA
# ═══════════════════════════════════════════════════════════════
def get_global_research(seen_keys=None, limit=10):
    seen_keys = seen_keys or []
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, u.full_name, u.username, u.profilepicurl, u.account_level,
                   pe.data as extras
            FROM posts p
            JOIN user_auth u ON u.user_key = p.user_key
            LEFT JOIN post_extras pe ON pe.post_key = p.post_key
            WHERE p.post_type = 'research'
            AND p.post_key != ALL(%s)
            AND p.visibility = 'public'
            ORDER BY p.created_at DESC
            LIMIT %s
        """, (seen_keys, limit))
        rows = cur.fetchall()
        cur.close()
        result = []
        for r in rows:
            d = dict(r)
            d['time_ago'] = time_ago(d.get('created_at'))
            result.append(d)
        return result
    finally:
        release_conn(conn)


def get_user_posts(user_key, tab, seen_keys=None):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        seen_keys = seen_keys or []

        if tab == 'posts':
            query = """
                SELECT p.*, u.full_name, u.username, u.profilepicurl, u.account_level,
                       pe.data as extras
                FROM posts p
                JOIN user_auth u ON u.user_key = p.user_key
                LEFT JOIN post_extras pe ON pe.post_key = p.post_key
                WHERE p.user_key = %s
                AND p.post_key != ALL(%s)
                AND p.post_type NOT IN ('research')
                ORDER BY p.created_at DESC
                LIMIT %s
            """
        elif tab == 'research':
            query = """
                SELECT p.*, u.full_name, u.username, u.profilepicurl, u.account_level,
                       pe.data as extras
                FROM posts p
                JOIN user_auth u ON u.user_key = p.user_key
                LEFT JOIN post_extras pe ON pe.post_key = p.post_key
                WHERE p.user_key = %s
                AND p.post_key != ALL(%s)
                AND p.post_type = 'research'
                ORDER BY p.created_at DESC
                LIMIT %s
            """
        elif tab == 'saved':
            query = """
                SELECT p.*, u.full_name, u.username, u.profilepicurl, u.account_level
                FROM posts p
                JOIN user_auth u ON u.user_key = p.user_key
                JOIN bookmarks b ON b.post_key = p.post_key
                WHERE b.user_key = %s
                AND p.post_key != ALL(%s)
                ORDER BY b.saved_at DESC
                LIMIT %s
            """
        else:
            return []

        cur.execute(query, (user_key, seen_keys, A.FEED_SCROLL_COUNT))
        posts = cur.fetchall()
        cur.close()
        return [dict(p) for p in posts]
    finally:
        release_conn(conn)

def get_followers(user_key):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.user_key, u.full_name, u.username, u.profilepicurl,
                   u.department, u.university, u.account_level
            FROM user_auth u
            JOIN follows f ON f.follower_key = u.user_key
            WHERE f.following_key = %s
            ORDER BY f.followed_at DESC
        """, (user_key,))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        release_conn(conn)

def get_following(user_key):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.user_key, u.full_name, u.username, u.profilepicurl,
                   u.department, u.university, u.account_level
            FROM user_auth u
            JOIN follows f ON f.following_key = u.user_key
            WHERE f.follower_key = %s
            ORDER BY f.followed_at DESC
        """, (user_key,))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        release_conn(conn)

def build_user_list_html(users, current_user_key):
    if not users:
        return A.nofollowingorfollowersgeneral
    html = ''
    for u in users:
        tick      = ' ✓' if u.get('account_level') == 'premium' else ''
        pic       = u.get('profilepicurl') or ''
        img_style = f'src="{pic}"' if pic else 'src="" style="display:none"'
        html += f'''<div class="user-item">
  <img {img_style} alt="profile">
  <div class="user-item-info">
    <div class="user-item-name">{u["full_name"]}{tick}</div>
    <div class="user-item-handle">@{u["username"]}</div>
    <div class="user-item-dept">{u.get("department","")} &bull; {u.get("university","")}</div>
  </div>
  <button class="user-follow-btn" onclick="toggleFollow('{u["user_key"]}',this)">Follow</button>
</div>'''
    return html

def update_avatar(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE user_auth SET profilepicurl = %s WHERE user_key = %s",
                    (x.get('profilepicurl', ''), user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Avatarupdatesuccessmessage,
                'avatar': x.get('profilepicurl', '')}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def remove_avatar(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE user_auth SET profilepicurl = '' WHERE user_key = %s", (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Avatarremovesuccessmessage, 'avatar': ''}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# TRENDING FEED
# ═══════════════════════════════════════════════════════════════
import random

def generate_feed_sequence(n):
    sequence     = []
    post_count   = 0
    last_type    = None
    streak       = 0
    post_types   = ['text', 'image', 'video', 'poll', 'event']

    for i in range(n):
        if post_count > 0 and post_count % A.TRENDING_FREQUENCY == 0:
            sequence.append('trending_now')

        if post_count > 0 and post_count % A.SUGGESTION_FREQUENCY == 0:
            if sequence and sequence[-1] == 'trending_now':
                sequence.insert(-1, 'suggestions')
            else:
                sequence.append('suggestions')

        if post_count > 0 and post_count % A.AD_FREQUENCY == 0:
            sequence.append('ad')

        available = post_types if streak < A.MAX_SAME_TYPE_IN_ROW else [t for t in post_types if t != last_type]
        chosen    = random.choice(available)

        if chosen == last_type:
            streak += 1
        else:
            streak    = 1
            last_type = chosen

        sequence.append(chosen)
        post_count += 1

    return sequence

def score_post(post, user, following_keys):
    score = 0
    score += post.get('like_count', 0)    * A.SCORE_LIKE
    score += post.get('comment_count', 0) * A.SCORE_COMMENT
    score += post.get('share_count', 0)   * A.SCORE_SHARE

    if post.get('university') == user.get('university'):
        score += A.SCORE_UNIVERSITY
    if post.get('department') == user.get('department'):
        score += A.SCORE_DEPARTMENT
    if post.get('academic_level') == user.get('academic_level'):
        score += A.SCORE_ACADEMIC_LEVEL
    if post.get('user_key') in following_keys:
        score += A.SCORE_FOLLOWING

    created_at = post.get('created_at')
    if created_at:
        diff_seconds = (datetime.utcnow() - created_at).total_seconds()
        if diff_seconds < 3600:
            score += A.SCORE_RECENCY_1HR
        elif diff_seconds < 21600:
            score += A.SCORE_RECENCY_6HR
        elif diff_seconds < 86400:
            score += A.SCORE_RECENCY_24HR

    return score

def get_scored_posts(user_key, seen_keys=None, n=None, type_filter=None):
    seen_keys = seen_keys or []
    n         = n or A.FEED_INITIAL_COUNT
    user      = get_user_by_key(user_key)
    conn      = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT following_key FROM follows WHERE follower_key = %s", (user_key,))
        following_keys = {row['following_key'] for row in cur.fetchall()}

        # Build type filter clause
        if type_filter and type_filter != 'all':
            type_clause = "AND p.post_type = %s"
            params = (user_key, seen_keys, type_filter, n * 3)
        else:
            type_clause = ""
            params = (user_key, seen_keys, n * 3)

        cur.execute(f"""
            SELECT p.*, u.full_name, u.username, u.profilepicurl,
                   u.university, u.department, u.academic_level, u.account_level,
                   pe.data as extras
            FROM posts p
            JOIN user_auth u ON u.user_key = p.user_key
            LEFT JOIN blocks b ON (b.blocker_key = %s AND b.blocked_key = p.user_key)
            LEFT JOIN post_extras pe ON pe.post_key = p.post_key
            WHERE p.post_key != ALL(%s)
            AND p.show_in_feed = TRUE
            AND p.visibility = 'public'
            AND b.blocker_key IS NULL
            {type_clause}
            ORDER BY p.created_at DESC
            LIMIT %s
        """, params)
        posts = [dict(p) for p in cur.fetchall()]
        cur.close()

        contextualized = []
        random_posts   = []

        for post in posts:
            post['score'] = score_post(post, user, following_keys)
            post['time_ago'] = time_ago(post.get('created_at'))
            if post.get('extras') is None:
                post['extras'] = {}

        posts.sort(key=lambda p: p['score'], reverse=True)

        split         = int(n * 0.7)
        contextualized = posts[:split]
        remaining      = posts[split:]
        random.shuffle(remaining)
        random_posts   = remaining[:n - split]

        final = contextualized + random_posts
        random.shuffle(random_posts)
        final = contextualized + random_posts
        final = final[:n]

        return final
    finally:
        release_conn(conn)

def get_suggestions(user_key, limit=5):
    user = get_user_by_key(user_key)
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.user_key, u.full_name, u.username, u.profilepicurl,
                   u.department, u.university, u.account_level,
                   u.numberoffollowers
            FROM user_auth u
            WHERE u.user_key != %s
            AND u.is_deactivated = FALSE
            AND u.user_key NOT IN (
                SELECT following_key FROM follows WHERE follower_key = %s
            )
            AND u.user_key NOT IN (
                SELECT blocked_key FROM blocks WHERE blocker_key = %s
            )
            ORDER BY
                CASE WHEN u.university = %s THEN 0 ELSE 1 END,
                CASE WHEN u.department = %s THEN 0 ELSE 1 END,
                u.numberoffollowers DESC
            LIMIT %s
        """, (user_key, user_key, user_key,
              user.get('university', ''), user.get('department', ''), limit))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        release_conn(conn)

def build_suggestions_html(users):
    if not users:
        return ''
    html = '<div class="suggestions-row">'
    for u in users:
        pic      = u.get('profilepicurl') or ''
        initials = ''.join([p[0].upper() for p in u['full_name'].split()[:2]])
        tick     = ' ✓' if u.get('account_level') == 'premium' else ''
        html += f'''<div class="suggestion-card">
  <div class="suggestion-avatar-wrap">
    {"<img src='"+pic+"' class='suggestion-avatar'>" if pic else f"<div class='suggestion-avatar-initials'>{initials}</div>"}
  </div>
  <div class="suggestion-name">{u["full_name"]}{tick}</div>
  <div class="suggestion-dept">{u.get("department","")}</div>
  <div class="suggestion-uni">{u.get("university","")}</div>
  <button class="suggestion-follow-btn" onclick="toggleFollow('{u["user_key"]}',this)">Follow</button>
</div>'''
    html += '</div>'
    return html

def get_trending_topics(limit=10):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT content FROM posts
            WHERE created_at > NOW() - INTERVAL '24 hours'
            AND visibility = 'public'
        """)
        posts     = cur.fetchall()
        cur.close()
        stopwords = {'the','a','an','is','are','was','were','i','you','we','they',
                     'it','he','she','and','or','but','in','on','at','to','for',
                     'of','with','this','that','be','have','do','not','my','your'}
        freq = {}
        for post in posts:
            words = post['content'].lower().split()
            for word in words:
                word = word.strip('.,!?#@()[]{}":;')
                if len(word) > 2 and word not in stopwords:
                    freq[word] = freq.get(word, 0) + 1
        sorted_topics = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{'topic': t[0], 'count': t[1]} for t in sorted_topics]
    finally:
        release_conn(conn)

def build_trending_topics_html(topics):
    if not topics:
        return ''
    html = '<div class="trending-topics-bar">'
    for t in topics:
        html += f'<span class="trending-topic" onclick="searchTopic(\'{t["topic"]}\')">{t["topic"]} <span class="topic-count">{t["count"]}</span></span>'
    html += '</div>'
    return html

def get_ad():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM ads WHERE active = TRUE
            ORDER BY RANDOM() LIMIT 1
        """)
        ad = cur.fetchone()
        cur.close()
        return dict(ad) if ad else None
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# SOCIAL ACTIONS
# ═══════════════════════════════════════════════════════════════
def toggle_like(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key = x.get('post_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM likes WHERE post_key=%s AND user_key=%s", (post_key, user_key))
        exists = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM likes WHERE post_key=%s AND user_key=%s", (post_key, user_key))
            cur.execute("UPDATE posts SET like_count = like_count - 1 WHERE post_key=%s", (post_key,))
            action = A.Unlikedmessage
        else:
            cur.execute("INSERT INTO likes (like_key, post_key, user_key) VALUES (%s,%s,%s)",
                        (gen_key(), post_key, user_key))
            cur.execute("UPDATE posts SET like_count = like_count + 1 WHERE post_key=%s", (post_key,))
            action = A.Likedmessage
            push_notification(
                recipient_key=get_post_owner(post_key),
                sender_key=user_key,
                notif_type='like',
                post_key=post_key,
                message=''
            )
        cur.execute("SELECT like_count FROM posts WHERE post_key=%s", (post_key,))
        count = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return {'status': 200, 'action': action, 'like_count': count}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def post_comment(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key = x.get('post_key')
    content  = x.get('content', '').strip()
    if not content:
        return {'status': 400, 'message': 'Comment cannot be empty.'}
    conn = get_conn()
    try:
        cur         = conn.cursor()
        comment_key = gen_key()
        cur.execute("""
            INSERT INTO comments (comment_key, post_key, user_key, content)
            VALUES (%s,%s,%s,%s)
        """, (comment_key, post_key, user_key, content))
        cur.execute("UPDATE posts SET comment_count = comment_count + 1 WHERE post_key=%s", (post_key,))
        push_notification(
            recipient_key=get_post_owner(post_key),
            sender_key=user_key,
            notif_type='comment',
            post_key=post_key,
            message=content[:100]
        )
        conn.commit()
        cur.close()
        user = get_user_by_key(user_key)
        return {
            'status': 200,
            'message': A.Commentsuccessmessage,
            'comment_key': comment_key,
            'full_name': user['full_name'],
            'profilepicurl': user.get('profilepicurl', ''),
            'time_ago': 'Just now',
            'content': content
        }
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def get_comments(x):
    post_key = x.get('post_key')
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.*, u.full_name, u.username, u.profilepicurl, u.account_level
            FROM comments c
            JOIN user_auth u ON u.user_key = c.user_key
            WHERE c.post_key = %s
            ORDER BY c.created_at ASC
        """, (post_key,))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        release_conn(conn)

def delete_comment(x, token):
    user_key    = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    comment_key = x.get('comment_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_key, post_key FROM comments WHERE comment_key=%s", (comment_key,))
        row = cur.fetchone()
        if not row:
            return {'status': 404, 'message': A.Commentnotfoundmsg}
        if row[0] != user_key:
            return {'status': 403, 'message': 'Not your comment.'}
        cur.execute("DELETE FROM comments WHERE comment_key=%s", (comment_key,))
        cur.execute("UPDATE posts SET comment_count = comment_count - 1 WHERE post_key=%s", (row[1],))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Commentdeletedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def toggle_bookmark(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key = x.get('post_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM bookmarks WHERE post_key=%s AND user_key=%s", (post_key, user_key))
        exists = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM bookmarks WHERE post_key=%s AND user_key=%s", (post_key, user_key))
            action = A.Unbookmarkedmessage
        else:
            cur.execute("INSERT INTO bookmarks (bookmark_key, post_key, user_key) VALUES (%s,%s,%s)",
                        (gen_key(), post_key, user_key))
            action = A.Bookmarkedmessage
        conn.commit()
        cur.close()
        return {'status': 200, 'action': action}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def toggle_follow(x, token):
    user_key   = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    target_key = x.get('target_key')
    if user_key == target_key:
        return {'status': 400, 'message': 'Cannot follow yourself.'}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM follows WHERE follower_key=%s AND following_key=%s",
                    (user_key, target_key))
        exists = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM follows WHERE follower_key=%s AND following_key=%s",
                        (user_key, target_key))
            cur.execute("UPDATE user_auth SET numberoffollowing = numberoffollowing - 1 WHERE user_key=%s", (user_key,))
            cur.execute("UPDATE user_auth SET numberoffollowers = numberoffollowers - 1 WHERE user_key=%s", (target_key,))
            action = A.Unfollowedmessage
        else:
            cur.execute("INSERT INTO follows (follow_key, follower_key, following_key) VALUES (%s,%s,%s)",
                        (gen_key(), user_key, target_key))
            cur.execute("UPDATE user_auth SET numberoffollowing = numberoffollowing + 1 WHERE user_key=%s", (user_key,))
            cur.execute("UPDATE user_auth SET numberoffollowers = numberoffollowers + 1 WHERE user_key=%s", (target_key,))
            action = A.Followedmessage
            push_notification(
                recipient_key=target_key,
                sender_key=user_key,
                notif_type='follow',
                post_key='',
                message=''
            )
        conn.commit()
        cur.close()
        return {'status': 200, 'action': action}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def toggle_block(x, token):
    user_key   = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    target_key = x.get('target_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM blocks WHERE blocker_key=%s AND blocked_key=%s",
                    (user_key, target_key))
        exists = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM blocks WHERE blocker_key=%s AND blocked_key=%s",
                        (user_key, target_key))
            action = A.Unblockedmessage
        else:
            cur.execute("INSERT INTO blocks (block_key, blocker_key, blocked_key) VALUES (%s,%s,%s)",
                        (gen_key(), user_key, target_key))
            # auto-unfollow both directions
            cur.execute("DELETE FROM follows WHERE (follower_key=%s AND following_key=%s) OR (follower_key=%s AND following_key=%s)",
                        (user_key, target_key, target_key, user_key))
            cur.execute("UPDATE user_auth SET numberoffollowing = (SELECT COUNT(*) FROM follows WHERE follower_key=user_auth.user_key) WHERE user_key IN (%s,%s)",
                        (user_key, target_key))
            cur.execute("UPDATE user_auth SET numberoffollowers = (SELECT COUNT(*) FROM follows WHERE following_key=user_auth.user_key) WHERE user_key IN (%s,%s)",
                        (user_key, target_key))
            action = A.Blockedmessage
        conn.commit()
        cur.close()
        return {'status': 200, 'action': action}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def vote_poll(x, token):
    user_key     = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key     = x.get('post_key')
    option_index = x.get('option_index')
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT 1 FROM poll_votes WHERE post_key=%s AND user_key=%s",
                    (post_key, user_key))
        if cur.fetchone():
            return {'status': 400, 'message': 'Already voted.'}
        cur.execute("INSERT INTO poll_votes (vote_key, post_key, user_key, option_index) VALUES (%s,%s,%s,%s)",
                    (gen_key(), post_key, user_key, option_index))
        cur.execute("SELECT data FROM post_extras WHERE post_key=%s", (post_key,))
        row  = cur.fetchone()
        data = row['data'] if row else {}
        options     = data.get('poll_options', [])
        total_votes = data.get('total_votes', 0) + 1
        if option_index < len(options):
            options[option_index]['votes'] = options[option_index].get('votes', 0) + 1
        data['total_votes'] = total_votes
        data['poll_options'] = options
        cur.execute("UPDATE post_extras SET data=%s WHERE post_key=%s",
                    (json.dumps(data), post_key))
        conn.commit()
        percentages = []
        for opt in options:
            pct = round((opt.get('votes', 0) / total_votes) * 100) if total_votes > 0 else 0
            percentages.append({'text': opt['text'], 'pct': pct, 'votes': opt.get('votes', 0)})
        cur.close()
        return {'status': 200, 'message': A.Votedmessage,
                'percentages': percentages, 'total_votes': total_votes}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def rsvp_event(x, token):
    user_key    = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key    = x.get('post_key')
    rsvp_status = x.get('rsvp_status')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO event_rsvps (rsvp_key, post_key, user_key, rsvp_status)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (post_key, user_key) DO UPDATE SET rsvp_status=%s
        """, (gen_key(), post_key, user_key, rsvp_status, rsvp_status))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.RSVPmessage, 'rsvp_status': rsvp_status}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def apply_bounty(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key = x.get('post_key')
    message  = x.get('message', '').strip()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM bounty_applications WHERE post_key=%s AND user_key=%s",
                    (post_key, user_key))
        if cur.fetchone():
            return {'status': 400, 'message': 'Already applied.'}
        cur.execute("""
            INSERT INTO bounty_applications (app_key, post_key, user_key, message)
            VALUES (%s,%s,%s,%s)
        """, (gen_key(), post_key, user_key, message))
        push_notification(
            recipient_key=get_post_owner(post_key),
            sender_key=user_key,
            notif_type='bounty_apply',
            post_key=post_key,
            message=message[:100]
        )
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Appliedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def get_post_owner(post_key):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_key FROM posts WHERE post_key=%s", (post_key,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# CREATE POST
# ═══════════════════════════════════════════════════════════════
def create_post(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}

    post_key    = gen_key()
    post_type   = x.get('type', 'text')
    content     = x.get('content', '').strip()
    media_url   = x.get('media', {}).get('url', '') if x.get('media') else ''
    media_type  = x.get('media', {}).get('type', '') if x.get('media') else ''
    visibility  = x.get('visibility', 'public')
    allow_comments = x.get('allowComments', True)
    show_in_feed   = x.get('showInFeed', True)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO posts
              (post_key, user_key, post_type, content, media_url, media_type,
               visibility, allow_comments, show_in_feed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (post_key, user_key, post_type, content, media_url, media_type,
              visibility, allow_comments, show_in_feed))

        extras = {}
        if post_type == 'poll':
            extras = {'poll_options': [{'text': o, 'votes': 0} for o in x.get('pollOptions', [])],
                      'total_votes': 0}
        elif post_type == 'research':
            extras = x.get('research', {})
        elif post_type == 'event':
            extras = x.get('event', {})
        elif post_type == 'bounty':
            extras = x.get('bounty', {})
        elif post_type == 'job':
            extras = x.get('job', {})
        elif post_type == 'product':
            extras = x.get('product', {})
        elif post_type == 'collab':
            extras = x.get('collab', {})
        elif post_type == 'ad':
            extras = x.get('ad', {})

        if extras:
            cur.execute("INSERT INTO post_extras (post_key, data) VALUES (%s,%s)",
                        (post_key, json.dumps(extras)))

        cur.execute("UPDATE user_auth SET numberofposts = numberofposts + 1 WHERE user_key=%s",
                    (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Postsuccessmessage, 'post_key': post_key}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def delete_post(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    post_key = x.get('post_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_key FROM posts WHERE post_key=%s", (post_key,))
        row = cur.fetchone()
        if not row:
            return {'status': 404, 'message': A.Postnotfoundmessage}
        if row[0] != user_key:
            return {'status': 403, 'message': 'Not your post.'}
        cur.execute("DELETE FROM posts WHERE post_key=%s", (post_key,))
        cur.execute("UPDATE user_auth SET numberofposts = numberofposts - 1 WHERE user_key=%s",
                    (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Postdeletedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════
def get_settings(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    user = get_user_by_key(user_key)
    payload = settings_payload(user)
    payload['status'] = 200
    payload['togglePrivate']           = 'active' if user.get('is_private') else ''
    payload['toggleActivity']          = 'active' if user.get('show_activity_status') else ''
    payload['toggleReadReceipts']      = 'active' if user.get('read_receipts') else ''
    payload['toggleTypingIndicators']  = 'active' if user.get('typing_indicators') else ''
    payload['toggleMessageRequests']   = 'active' if user.get('message_requests_filter') == 'everyone' else ''
    payload['togglePush']              = 'active' if user.get('notif_push') else ''
    payload['toggleLikes']             = 'active' if user.get('notif_likes') else ''
    payload['toggleComments']          = 'active' if user.get('notif_comments') else ''
    payload['toggleFollowers']         = 'active' if user.get('notif_follows') else ''
    payload['toggleDMs']               = 'active' if user.get('notif_messages') else ''
    payload['toggleMentions']          = 'active' if user.get('notif_mentions') else ''
    payload['toggleBounties']          = 'active' if user.get('notif_bounties') else ''
    payload['toggleEvents']            = 'active' if user.get('notif_events') else ''
    payload['toggleResearch']          = 'active' if user.get('notif_email') else ''
    payload['toggleEmail']             = 'active' if user.get('notif_email') else ''
    payload['selectPostVisibility']    = user.get('post_visibility', 'public')
    payload['selectResearchVisibility']= user.get('research_visibility', 'public')
    payload['selectMessagePrivacy']    = user.get('message_privacy', 'everyone')
    payload['selectTagPrivacy']        = user.get('tag_privacy', 'everyone')
    payload['selectFollowersVisibility']= user.get('followers_list_visibility', 'everyone')
    return payload

def update_email(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    user = get_user_by_key(user_key)
    if not check_password(x.get('password', ''), user['password']):
        return {'status': 400, 'message': A.Incorrectpasswordmessage}
    new_email = x.get('new_email', '').strip().lower()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM user_auth WHERE email=%s AND user_key!=%s", (new_email, user_key))
        if cur.fetchone():
            return {'status': 400, 'message': A.Emailalreadyexistsmessage}
        cur.execute("UPDATE user_auth SET email=%s WHERE user_key=%s", (new_email, user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Emailupdatesuccessmessage, 'setEmail': new_email}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_username(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    new_username = x.get('new_username', '').strip().lower()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM user_auth WHERE username=%s AND user_key!=%s", (new_username, user_key))
        if cur.fetchone():
            return {'status': 400, 'message': A.Usernamealreadyexistsmessage}
        cur.execute("UPDATE user_auth SET username=%s WHERE user_key=%s", (new_username, user_key))
        conn.commit()
        cur.close()
        user = get_user_by_key(user_key)
        return {'status': 200, 'message': A.Usernameupdatesuccessmessage,
                'setUsername': f'@{new_username}',
                'setProfileHandle': f"@{new_username} &bull; {user.get('department','')} &bull; {user.get('university','')}"}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_bio(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    new_bio = x.get('new_bio', '').strip()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE user_auth SET biodescription=%s WHERE user_key=%s", (new_bio, user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Bioupdatesuccessmessage, 'setBio': new_bio}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_password(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    user = get_user_by_key(user_key)
    if not check_password(x.get('current_password', ''), user['password']):
        return {'status': 400, 'message': A.Incorrectpasswordmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE user_auth SET password=%s, last_password_change=NOW()
            WHERE user_key=%s
        """, (hash_password(x.get('new_password', '')), user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Passwordupdatesuccessmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_profile_info(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE user_auth SET
              full_name=%s, university=%s, department=%s, academic_level=%s
            WHERE user_key=%s
        """, (x.get('full_name',''), x.get('university',''),
              x.get('department',''), x.get('academic_level',''), user_key))
        conn.commit()
        cur.close()
        user = get_user_by_key(user_key)
        return {'status': 200, 'message': A.Profileupdatesuccessmessage,
                'setProfileName': user['full_name'],
                'setProfileHandle': f"@{user['username']} &bull; {user.get('department','')} &bull; {user.get('university','')}",
                'info': profileinfo(user)}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_privacy_settings(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    allowed = ['is_private','show_activity_status','post_visibility','research_visibility',
               'message_privacy','tag_privacy','followers_list_visibility']
    conn = get_conn()
    try:
        cur = conn.cursor()
        for field in allowed:
            if field in x:
                cur.execute(f"UPDATE user_auth SET {field}=%s WHERE user_key=%s",
                            (x[field], user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Settingsupdatedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_notification_settings(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    allowed = ['notif_likes','notif_comments','notif_follows','notif_mentions',
               'notif_messages','notif_events','notif_bounties','notif_email','notif_push']
    conn = get_conn()
    try:
        cur = conn.cursor()
        for field in allowed:
            if field in x:
                cur.execute(f"UPDATE user_auth SET {field}=%s WHERE user_key=%s",
                            (x[field], user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Settingsupdatedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_messaging_settings(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    allowed = ['read_receipts','typing_indicators','message_requests_filter']
    conn = get_conn()
    try:
        cur = conn.cursor()
        for field in allowed:
            if field in x:
                cur.execute(f"UPDATE user_auth SET {field}=%s WHERE user_key=%s",
                            (x[field], user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Settingsupdatedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def update_appearance(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    allowed = ['theme','font_size','compact_mode']
    conn = get_conn()
    try:
        cur = conn.cursor()
        for field in allowed:
            if field in x:
                cur.execute(f"UPDATE user_auth SET {field}=%s WHERE user_key=%s",
                            (x[field], user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'message': A.Settingsupdatedmessage}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def get_blocked_users(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT u.user_key, u.full_name, u.username, u.profilepicurl
            FROM user_auth u
            JOIN blocks b ON b.blocked_key = u.user_key
            WHERE b.blocker_key=%s
            ORDER BY b.blocked_at DESC
        """, (user_key,))
        rows = cur.fetchall()
        cur.close()
        return {'status': 200, 'blocked': [dict(r) for r in rows]}
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════
def search(x, token):
    user_key = validate_session(token)
    query    = x.get('query', '').strip()
    if not query:
        return {'status': 200, 'results': [], 'message': A.Nosearchresultsmessage}
    conn = get_conn()
    try:
        cur     = conn.cursor(cursor_factory=RealDictCursor)
        pattern = f'%{query}%'

        cluster = get_cluster_weights(query)
        cluster_terms = list(cluster.keys())

        cur.execute("""
            SELECT p.post_key, p.post_type, p.content, p.like_count,
                   p.comment_count, p.created_at,
                   u.full_name, u.username, u.profilepicurl, u.account_level
            FROM posts p
            JOIN user_auth u ON u.user_key = p.user_key
            WHERE p.content ILIKE %s AND p.visibility = 'public'
            ORDER BY p.like_count DESC
            LIMIT 20
        """, (pattern,))
        post_results = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT user_key, full_name, username, profilepicurl,
                   department, university, account_level, numberoffollowers
            FROM user_auth
            WHERE (full_name ILIKE %s OR username ILIKE %s)
            AND is_deactivated = FALSE
            LIMIT 10
        """, (pattern, pattern))
        user_results = [dict(r) for r in cur.fetchall()]

        cur.close()
        return {
            'status': 200,
            'posts': post_results,
            'users': user_results,
            'cluster_suggestions': cluster_terms[:5]
        }
    finally:
        release_conn(conn)

def record_search_pair(x):
    query    = x.get('query', '').strip().lower()
    selected = x.get('selected', '').strip().lower()
    if not query or not selected or query == selected:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO search_pairs (pair_key, query, selected, weight)
            VALUES (%s, %s, %s, 1.0)
            ON CONFLICT (query, selected) DO UPDATE
              SET weight = search_pairs.weight + 0.5,
                  last_searched = NOW()
        """, (gen_key(), query, selected))
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
    finally:
        release_conn(conn)

def get_cluster_weights(query):
    query = query.strip().lower()
    conn  = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT selected, weight FROM search_pairs
            WHERE query = %s
            ORDER BY weight DESC
            LIMIT 10
        """, (query,))
        rows = cur.fetchall()
        cur.close()
        return {r['selected']: r['weight'] for r in rows}
    finally:
        release_conn(conn)

# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
def push_notification(recipient_key, sender_key, notif_type, post_key, message):
    if not recipient_key or recipient_key == sender_key:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO notifications
              (notif_key, recipient_key, sender_key, notif_type, post_key, message)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (gen_key(), recipient_key, sender_key, notif_type, post_key, message))
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
    finally:
        release_conn(conn)

def get_notifications(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT n.*, u.full_name, u.username, u.profilepicurl
            FROM notifications n
            LEFT JOIN user_auth u ON u.user_key = n.sender_key
            WHERE n.recipient_key = %s
            ORDER BY n.created_at DESC
            LIMIT 50
        """, (user_key,))
        rows = cur.fetchall()
        cur.close()
        return {'status': 200, 'notifications': [dict(r) for r in rows]}
    finally:
        release_conn(conn)

def mark_notification_read(x, token):
    user_key  = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    notif_key = x.get('notif_key')
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE notifications SET is_read=TRUE WHERE notif_key=%s AND recipient_key=%s",
                    (notif_key, user_key))
        conn.commit()
        cur.close()
        return {'status': 200}
    finally:
        release_conn(conn)

def mark_all_notifications_read(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE notifications SET is_read=TRUE WHERE recipient_key=%s", (user_key,))
        conn.commit()
        cur.close()
        return {'status': 200}
    finally:
        release_conn(conn)

def get_unread_notif_count(token):
    user_key = validate_session(token)
    if not user_key:
        return 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM notifications
            WHERE recipient_key=%s AND is_read=FALSE
        """, (user_key,))
        count = cur.fetchone()[0]
        cur.close()
        return count
    finally:
        release_conn(conn)

# ═══════════════════════════════════════════════════════════════
# MESSAGES
# ═══════════════════════════════════════════════════════════════
def get_conversations(token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.convo_key,
                   CASE WHEN c.user_a_key=%s THEN c.user_b_key ELSE c.user_a_key END as other_key,
                   u.full_name, u.username, u.profilepicurl, u.account_level,
                   u.show_activity_status, u.last_seen,
                   (SELECT content FROM messages m WHERE m.convo_key=c.convo_key
                    ORDER BY m.sent_at DESC LIMIT 1) as last_msg,
                   (SELECT sent_at FROM messages m WHERE m.convo_key=c.convo_key
                    ORDER BY m.sent_at DESC LIMIT 1) as last_msg_time,
                   (SELECT COUNT(*) FROM messages m WHERE m.convo_key=c.convo_key
                    AND m.sender_key != %s AND m.is_read=FALSE) as unread_count
            FROM conversations c
            JOIN user_auth u ON u.user_key =
                CASE WHEN c.user_a_key=%s THEN c.user_b_key ELSE c.user_a_key END
            WHERE c.user_a_key=%s OR c.user_b_key=%s
            ORDER BY last_msg_time DESC NULLS LAST
        """, (user_key, user_key, user_key, user_key, user_key))
        rows = cur.fetchall()
        cur.close()
        return {'status': 200, 'conversations': [dict(r) for r in rows]}
    finally:
        release_conn(conn)

def get_or_create_conversation(user_key, other_key):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT convo_key FROM conversations
            WHERE (user_a_key=%s AND user_b_key=%s)
               OR (user_a_key=%s AND user_b_key=%s)
        """, (user_key, other_key, other_key, user_key))
        row = cur.fetchone()
        if row:
            cur.close()
            return row['convo_key']
        convo_key = gen_key()
        cur.execute("INSERT INTO conversations (convo_key, user_a_key, user_b_key) VALUES (%s,%s,%s)",
                    (convo_key, user_key, other_key))
        conn.commit()
        cur.close()
        return convo_key
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def get_dm_messages(x, token):
    user_key  = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    convo_key = x.get('convo_key')
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT m.*, u.full_name, u.username, u.profilepicurl
            FROM messages m
            JOIN user_auth u ON u.user_key = m.sender_key
            WHERE m.convo_key=%s
            ORDER BY m.sent_at ASC
        """, (convo_key,))
        rows = cur.fetchall()
        cur.execute("UPDATE messages SET is_read=TRUE WHERE convo_key=%s AND sender_key!=%s",
                    (convo_key, user_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'messages': [dict(r) for r in rows]}
    finally:
        release_conn(conn)

def send_dm(x, token):
    user_key     = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    recipient_key = x.get('recipient_key')
    content       = x.get('content', '').strip()
    media_url     = x.get('media_url', '')
    reply_to_key  = x.get('reply_to_key', '')
    if not content and not media_url:
        return {'status': 400, 'message': 'Message cannot be empty.'}
    convo_key = get_or_create_conversation(user_key, recipient_key)
    conn = get_conn()
    try:
        cur     = conn.cursor()
        msg_key = gen_key()
        cur.execute("""
            INSERT INTO messages (msg_key, convo_key, sender_key, content, media_url, reply_to_key)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (msg_key, convo_key, user_key, content, media_url, reply_to_key))
        push_notification(
            recipient_key=recipient_key,
            sender_key=user_key,
            notif_type='message',
            post_key='',
            message=content[:100]
        )
        conn.commit()
        cur.close()
        return {'status': 200, 'msg_key': msg_key, 'convo_key': convo_key,
                'sent_at': datetime.utcnow().isoformat()}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)

def get_global_messages():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT g.*, u.full_name, u.username, u.profilepicurl, u.account_level
            FROM global_chat g
            JOIN user_auth u ON u.user_key = g.user_key
            ORDER BY g.sent_at DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        cur.close()
        return {'status': 200, 'messages': [dict(r) for r in reversed(rows)]}
    finally:
        release_conn(conn)

def send_global_message(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    content = x.get('content', '').strip()
    if not content:
        return {'status': 400, 'message': 'Message cannot be empty.'}
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO global_chat (msg_key, user_key, content) VALUES (%s,%s,%s)",
                    (gen_key(), user_key, content))
        conn.commit()
        cur.close()
        user = get_user_by_key(user_key)
        return {'status': 200, 'full_name': user['full_name'],
                'profilepicurl': user.get('profilepicurl',''),
                'content': content, 'sent_at': datetime.utcnow().isoformat()}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════════
# FRONTEND PERSONALIZER
# ═══════════════════════════════════════════════════════════════
def Frontend_personalizer(x, user, token=None):
    ans = {}

    # ── Profile page ──────────────────────────────────────────
    ans['profilenav'] = drawerprofilenav(user)
    ans['info']       = profileinfo(user)
    ans['stats']      = profilestats(user)
    ans['avatar']     = get_avatar_html(user)

    # ── Followers/Following modal ──────────────────────────────
    ans['userListContent'] = A.nofollowingorfollowersgeneral

    # ── Profile tabs ──────────────────────────────────────────
    ans['tab-posts']    = A.nopostonsignup
    ans['tab-research'] = A.nopostresearchonsignup
    ans['tab-saved']    = A.nopostsavedonsignup

    # ── Settings ──────────────────────────────────────────────
    s = settings_payload(user)
    for key, val in s.items():
        ans[key] = val

    # ── Notification badge ────────────────────────────────────
    ans['notif_count'] = 0

    # ── Trending initial sequence ──────────────────────────────
    ans['feed_sequence'] = generate_feed_sequence(A.FEED_INITIAL_COUNT)

    # ── Suggestions ───────────────────────────────────────────
    suggestions = get_suggestions(user['user_key'])
    ans['suggestions_html'] = build_suggestions_html(suggestions)

    # ── Trending topics ───────────────────────────────────────
    topics = get_trending_topics()
    ans['trending_topics_html'] = build_trending_topics_html(topics)

    # ── Feed config sent to JS ────────────────────────────────
    ans['feed_config'] = {
        'initial_count':  A.FEED_INITIAL_COUNT,
        'scroll_count':   A.FEED_SCROLL_COUNT,
        'max_dom':        A.FEED_MAX_DOM,
        'scroll_trigger': A.FEED_SCROLL_TRIGGER
    }

    # ── Session info ──────────────────────────────────────────
    ans['user_key'] = user['user_key']
    ans['token']    = token

    return ans


# ═══════════════════════════════════════════════════════════════
# FRONTEND REQUEST EXECUTOR
# ═══════════════════════════════════════════════════════════════
def Frontend_request_executor(x, token=None):
    status = x.get('status', '')

    # ── SIGNUP ────────────────────────────────────────────────
    if status == 'signup':
        check = verify_signup_data(x)
        if check['status'] != 200:
            msg_map = {
                'both':     A.Emailandusernameexistonsignupmessage,
                'email':    A.Emailexistonsignupmessage,
                'username': A.Usernameexistonsignupmessage,
            }
            return {'status': 400, 'message': msg_map.get(check.get('error'), A.Genericerror)}
        user_key = insert_user(x)
        new_token = create_session(user_key)
        user      = get_user_by_key(user_key)
        ans       = {'status': 200, 'message': A.Successfulsignupmessage}
        ans      |= Frontend_personalizer(x, user, new_token)
        return ans

    # ── SIGNIN ────────────────────────────────────────────────
    elif status == 'signin':
        check = verify_signin_data(x)
        if check['status'] != 200:
            msg_map = {
                'credentials': A.Invalidcredentialsmessage,
                'deactivated': A.Accountdeactivatedmessage,
            }
            return {'status': 400, 'message': msg_map.get(check.get('error'), A.Genericerror)}
        user_key  = check['user_key']
        new_token = create_session(user_key)
        user      = get_user_by_key(user_key)
        update_last_seen(user_key)
        # Signin loads real data
        followers_data = get_followers(user_key)
        following_data = get_following(user_key)
        posts_data     = get_user_posts(user_key, 'posts')
        research_data  = get_user_posts(user_key, 'research')
        saved_data     = get_user_posts(user_key, 'saved')
        notif_count    = get_unread_notif_count(new_token)
        ans            = {'status': 200, 'message': A.Successfulsigninmessage}
        ans           |= Frontend_personalizer(x, user, new_token)
        ans['userListContent'] = build_user_list_html(following_data, user_key)
        ans['notif_count']     = notif_count
        return ans

    # ── LOGOUT ────────────────────────────────────────────────
    elif status == 'logout':
        return logout(token)

    # ── FEED ──────────────────────────────────────────────────
    elif status == 'get_feed':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        seen_keys   = x.get('seen_keys', [])
        n           = x.get('n', A.FEED_SCROLL_COUNT)
        type_filter = x.get('type_filter', None)
        posts       = get_scored_posts(user_key, seen_keys, n, type_filter)
        sequence    = generate_feed_sequence(n)
        return {'status': 200, 'posts': posts, 'sequence': sequence}

    elif status == 'get_suggestions':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        users = get_suggestions(user_key)
        return {'status': 200, 'suggestions_html': build_suggestions_html(users)}

    elif status == 'get_trending_topics':
        topics = get_trending_topics()
        return {'status': 200, 'trending_topics_html': build_trending_topics_html(topics)}

    # ── SOCIAL ────────────────────────────────────────────────
    elif status == 'toggle_like':     return toggle_like(x, token)
    elif status == 'post_comment':    return post_comment(x, token)
    elif status == 'get_comments':    return {'status': 200, 'comments': get_comments(x)}
    elif status == 'delete_comment':  return delete_comment(x, token)
    elif status == 'toggle_bookmark': return toggle_bookmark(x, token)
    elif status == 'toggle_follow':   return toggle_follow(x, token)
    elif status == 'toggle_block':    return toggle_block(x, token)
    elif status == 'vote_poll':       return vote_poll(x, token)
    elif status == 'rsvp_event':      return rsvp_event(x, token)
    elif status == 'apply_bounty':    return apply_bounty(x, token)

    # ── CREATE ────────────────────────────────────────────────
    elif status == 'create_post':  return create_post(x, token)
    elif status == 'delete_post':  return delete_post(x, token)

    # ── PROFILE ───────────────────────────────────────────────
    elif status == 'get_profile':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        user = get_user_by_key(user_key)
        return {
            'status':    200,
            'full_name': user['full_name'],
            'username':  user['username'],
            'bio':       user.get('biodescription', ''),
            'avatar':    user.get('profilepicurl') or A.defaultavatarurl,
            'following': user.get('numberoffollowing', 0),
            'followers': user.get('numberoffollowers', 0),
            'likes':     user.get('numberoflikes', 0),
            'posts':     user.get('numberofposts', 0),
        }

    elif status == 'get_global_research':
        seen_keys = x.get('seen_keys', [])
        posts     = get_global_research(seen_keys)
        return {'status': 200, 'posts': posts}

    elif status == 'get_user_posts':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        tab       = x.get('tab', 'posts')
        seen_keys = x.get('seen_keys', [])
        posts     = get_user_posts(user_key, tab, seen_keys)
        return {'status': 200, 'posts': posts}

    elif status == 'get_followers':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        target   = x.get('target_key', user_key)
        users    = get_followers(target)
        return {'status': 200, 'userListContent': build_user_list_html(users, user_key)}

    elif status == 'get_following':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        target   = x.get('target_key', user_key)
        users    = get_following(target)
        return {'status': 200, 'userListContent': build_user_list_html(users, user_key)}

    elif status == 'update_avatar':   return update_avatar(x, token)
    elif status == 'remove_avatar':   return remove_avatar(token)

    # ── SETTINGS ──────────────────────────────────────────────
    elif status == 'get_settings':              return get_settings(token)
    elif status == 'update_email':              return update_email(x, token)
    elif status == 'update_username':           return update_username(x, token)
    elif status == 'update_bio':                return update_bio(x, token)
    elif status == 'update_password':           return update_password(x, token)
    elif status == 'update_profile_info':       return update_profile_info(x, token)
    elif status == 'update_privacy_settings':   return update_privacy_settings(x, token)
    elif status == 'update_notification_settings': return update_notification_settings(x, token)
    elif status == 'update_messaging_settings': return update_messaging_settings(x, token)
    elif status == 'update_appearance':         return update_appearance(x, token)
    elif status == 'get_blocked_users':         return get_blocked_users(token)
    elif status == 'deactivate_account':        return deactivate_account(x, token)
    elif status == 'delete_account':            return delete_account(x, token)

    # ── SEARCH ────────────────────────────────────────────────
    elif status == 'search':              return search(x, token)
    elif status == 'record_search_pair':  record_search_pair(x); return {'status': 200}

    # ── NOTIFICATIONS ─────────────────────────────────────────
    elif status == 'get_notifications':         return get_notifications(token)
    elif status == 'mark_notification_read':    return mark_notification_read(x, token)
    elif status == 'mark_all_notifications_read': return mark_all_notifications_read(token)
    elif status == 'get_unread_notif_count':
        return {'status': 200, 'count': get_unread_notif_count(token)}

    # ── MESSAGES ──────────────────────────────────────────────
    elif status == 'get_conversations':   return get_conversations(token)
    elif status == 'get_dm_messages':     return get_dm_messages(x, token)
    elif status == 'send_dm':             return send_dm(x, token)
    elif status == 'get_global_messages': return get_global_messages()
    elif status == 'send_global_message': return send_global_message(x, token)

    # ── UNKNOWN ───────────────────────────────────────────────
    else:
        return {'status': 400, 'message': A.Genericerror}


# ── Startup ───────────────────────────────────────────────────
create_table()
