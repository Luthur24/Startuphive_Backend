# ═══════════════════════════════════════════════════════════════
# APPMODULATOR.PY — Treℵds Platform Configuration
# ═══════════════════════════════════════════════════════════════
import os

# ── DATABASE ────────────────────────────────────────────────────
_db_url = os.environ.get('DATABASE_URL', '')

if _db_url:
    import urllib.parse as _up
    _r          = _up.urlparse(_db_url)
    DB_HOST     = _r.hostname
    DB_NAME     = _r.path.lstrip('/').split('?')[0]
    DB_USER     = _r.username
    DB_PASSWORD = _r.password
    DB_PORT     = _r.port or 5432
else:
    DB_HOST     = "dpg-d70himndiees73dlbeig-a.frankfurt-postgres.render.com"
    DB_NAME     = "trends_db2"
    DB_USER     = "trends_db2_user"
    DB_PASSWORD = "h5NO8WY8nxLF64WSM7jwYZ7b8B7dCOiR"
    DB_PORT     = 5432

# ── CLOUDINARY ──────────────────────────────────────────────────
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'ddusfl7pi')
CLOUDINARY_API_KEY    = os.environ.get('CLOUDINARY_API_KEY',    '599965682593626')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'pUcb90_1jtv-rDlHXRRsfDcBK5k')

# ── SESSION ─────────────────────────────────────────────────────
SECRET_KEY            = os.environ.get('SECRET_KEY', 'treands_secret_key_change_in_production')
SESSION_DURATION_DAYS = 30

# ── AUTH MESSAGES ───────────────────────────────────────────────
Emailandusernameexistonsignupmessage = "An account with this email and username already exists."
Emailexistonsignupmessage            = "An account with this email already exists."
Usernameexistonsignupmessage         = "This username is already taken."
Successfulsignupmessage              = "Welcome to Treℵds."
Successfulsigninmessage              = "Welcome back."
Invalidcredentialsmessage            = "Invalid email or password."
Accountdeactivatedmessage            = "This account has been deactivated."
Sessionexpiredmessage                = "Your session has expired. Please sign in again."
Genericerror                         = "Something went wrong. Please try again."
Unauthorizedmessage                  = "Unauthorized. Please sign in."

# ── PROFILE DEFAULTS ────────────────────────────────────────────
defaultbiodescription = "Esse quam videri."
defaultavatarurl      = "https://raw.githubusercontent.com/luthur24/Trends/main/volodymyr-dobrovolskyy-QlM0NtVqcgc-unsplash.jpg"

# ── EMPTY STATE MESSAGES ────────────────────────────────────────
nofollowingorfollowersgeneral = "<div class='empty-tab'>Nothing here yet.</div>"
nopostonsignup                = "<div class='userpostedstuffs'>A blank feed is a rare thing. Fill it with something that matters.</div>"
nopostresearchonsignup        = "<div class='userpostedstuffs'>No research posted yet.</div>"
nopostsavedonsignup           = "<div class='userpostedstuffs'>Nothing saved yet.</div>"
emptyfeedmessage              = "<div class='userpostedstuffs'>The feed is quiet. Be the first to say something worth reading.</div>"
emptynotificationsmessage     = "<div class='empty-tab'>No notifications yet.</div>"
emptyconversationsmessage     = "<div class='empty-tab'>No messages yet.</div>"
emptysearchmessage            = "<div class='empty-tab'>No results found.</div>"
emptyglobalchatmessage        = "<div class='empty-tab'>No messages in global chat yet.</div>"

# ── SETTINGS MESSAGES ───────────────────────────────────────────
Emailupdatesuccessmessage    = "Email updated successfully."
Usernameupdatesuccessmessage = "Username updated successfully."
Passwordupdatesuccessmessage = "Password updated successfully."
Profileupdatesuccessmessage  = "Profile updated successfully."
Bioupdatesuccessmessage      = "Bio updated successfully."
Avatarupdatesuccessmessage   = "Profile photo updated."
Avatarremovesuccessmessage   = "Profile photo removed."
Incorrectpasswordmessage     = "Incorrect password."
Emailalreadyexistsmessage    = "This email is already in use."
Usernamealreadyexistsmessage = "This username is already taken."
Settingsupdatedmessage       = "Settings updated."
Accountdeactivatesuccessmsg  = "Account deactivated. You can reactivate by signing in."
Accountdeletesuccessmsg      = "Account permanently deleted."

# ── SOCIAL MESSAGES ─────────────────────────────────────────────
Postsuccessmessage    = "Post created."
Postdeletedmessage    = "Post deleted."
Commentsuccessmessage = "Comment posted."
Commentdeletedmessage = "Comment deleted."
Likedmessage          = "liked"
Unlikedmessage        = "unliked"
Followedmessage       = "followed"
Unfollowedmessage     = "unfollowed"
Blockedmessage        = "blocked"
Unblockedmessage      = "unblocked"
Bookmarkedmessage     = "bookmarked"
Unbookmarkedmessage   = "unbookmarked"
Votedmessage          = "Vote recorded."
RSVPmessage           = "RSVP updated."
Appliedmessage        = "Application submitted."
Postnotfoundmessage   = "Post not found."
Commentnotfoundmsg    = "Comment not found."

# ── SEARCH MESSAGES ─────────────────────────────────────────────
Nosearchresultsmessage = "No results found."

# ── FEED DEFAULTS ───────────────────────────────────────────────
FEED_INITIAL_COUNT   = 20
FEED_SCROLL_COUNT    = 10
FEED_MAX_DOM         = 50
FEED_SCROLL_TRIGGER  = 4
AD_FREQUENCY         = 8
TRENDING_FREQUENCY   = 5
SUGGESTION_FREQUENCY = 10
MAX_SAME_TYPE_IN_ROW = 4

# ── SCORING WEIGHTS ─────────────────────────────────────────────
SCORE_LIKE           = 1
SCORE_COMMENT        = 2
SCORE_SHARE          = 1.5
SCORE_UNIVERSITY     = 20
SCORE_DEPARTMENT     = 15
SCORE_ACADEMIC_LEVEL = 10
SCORE_FOLLOWING      = 40
SCORE_RECENCY_1HR    = 50
SCORE_RECENCY_6HR    = 30
SCORE_RECENCY_24HR   = 10
