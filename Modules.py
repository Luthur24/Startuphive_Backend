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
        else:
            type_clause = ""
            type_filter = None

        if type_filter:
            params = (user_key, user_key, user_key, user_key, seen_keys, type_filter, n * 3)
        else:
            params = (user_key, user_key, user_key, user_key, seen_keys, n * 3)

        cur.execute(f"""
            SELECT p.*, u.full_name, u.username, u.profilepicurl,
                   u.university, u.department, u.academic_level, u.account_level,
                   pe.data as extras,
                   EXISTS(SELECT 1 FROM likes l WHERE l.post_key = p.post_key AND l.user_key = %s) as is_liked,
                   EXISTS(SELECT 1 FROM bookmarks bk WHERE bk.post_key = p.post_key AND bk.user_key = %s) as is_bookmarked,
       EXISTS(SELECT 1 FROM follows f WHERE f.follower_key = %s AND f.following_key = p.user_key) as is_following
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
    # Prevent self-like
    c0 = get_conn()
    try:
        r0 = c0.cursor(cursor_factory=RealDictCursor)
        r0.execute("SELECT user_key FROM posts WHERE post_key=%s", (post_key,))
        owner = r0.fetchone()
        if owner and owner['user_key'] == user_key:
            return {'status': 400, 'message': "You can't like your own post"}
    finally:
        release_conn(c0)
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
def upload_to_cloudinary(data_url, resource_type='image'):
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name = A.CLOUDINARY_CLOUD_NAME,
            api_key    = A.CLOUDINARY_API_KEY,
            api_secret = A.CLOUDINARY_API_SECRET
        )
        result = cloudinary.uploader.upload(data_url, resource_type=resource_type, folder='trends_posts')
        return result.get('secure_url', '')
    except Exception as e:
        print(f'[Cloudinary] Upload failed: {e}')
        return data_url

def create_post(x, token):
    user_key = validate_session(token)
    if not user_key:
        return {'status': 401, 'message': A.Unauthorizedmessage}
    # Validate post types
    import datetime as _dtv
    _ptype = x.get('type','text')
    if _ptype == 'event':
        _ed = (x.get('event') or {}).get('date','')
        if _ed:
            try:
                if _dtv.datetime.strptime(_ed,'%Y-%m-%d').date() < _dtv.date.today():
                    return {'status':400,'message':'Event date must be in the future'}
            except: pass
    if _ptype == 'bounty':
        try:
            if float((x.get('bounty') or {}).get('amount',0) or 0) <= 0:
                return {'status':400,'message':'Bounty reward must be greater than 0'}
        except: pass
    if _ptype == 'research':
        if not (x.get('research') or {}).get('title','').strip():
            return {'status':400,'message':'Research post requires a title'}

    post_key       = gen_key()
    post_type      = x.get('type', 'text')
    content        = x.get('content', '').strip()
    media_url      = x.get('media', {}).get('url', '') if x.get('media') else ''
    media_type     = x.get('media', {}).get('type', '') if x.get('media') else ''
    visibility     = x.get('visibility', 'public')
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

        hashtags = x.get('hashtags', [])

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
        elif post_type == 'question':
            extras = x.get('question', {})
        elif post_type == 'ad':
            extras = x.get('ad', {})

        if hashtags:
            extras['hashtags'] = hashtags

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
                'setUsername': f'{new_username}',
                'setProfileHandle': f"{new_username} &bull; {user.get('department','')} &bull; {user.get('university','')}"}
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
        # Build dynamic update - only update fields that were sent
        fields = []
        vals = []
        for col in ['full_name', 'university', 'department', 'academic_level', 'bio']:
            if col in x and x[col] is not None:
                fields.append(f"{col}=%s")
                vals.append(x[col])
        if not fields:
            return {'status': 400, 'message': 'Nothing to update.'}
        vals.append(user_key)
        cur.execute(f"UPDATE user_auth SET {', '.join(fields)} WHERE user_key=%s", vals)
        conn.commit()
        cur.close()
        user = get_user_by_key(user_key)
        return {'status': 200, 'message': A.Profileupdatesuccessmessage,
                'setProfileName': user['full_name'],
                'setProfileHandle': f"{user['username']} &bull; {user.get('department','')} &bull; {user.get('university','')}",
                'department': user.get('department',''),
            'university':  user.get('university',''),
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
            WHERE (p.content ILIKE %s OR COALESCE(pe.data::text,'') ILIKE %s)
            AND p.visibility = 'public'
            ORDER BY p.like_count DESC
            LIMIT 20
        """, (pattern, pattern))
        post_results = []
        for r in cur.fetchall():
            p = dict(r)
            p['time_ago'] = time_ago(p.get('created_at'))
            p['extras'] = {}
            p['is_liked'] = False
            p['is_bookmarked'] = False
            p['is_following'] = False
            post_results.append(p)

        cur.execute("""
            SELECT user_key, full_name, username, profilepicurl,
                   department, university, account_level, numberoffollowers
            FROM user_auth
            WHERE (full_name ILIKE %s OR username ILIKE %s)
            AND is_deactivated = FALSE
            LIMIT 10
        """, (pattern, pattern))
        user_results = [dict(r) for r in cur.fetchall()]
        # Check follow status for each user
        if user_key:
            for u in user_results:
                cur.execute("SELECT 1 FROM follows WHERE follower_key=%s AND following_key=%s", (user_key, u['user_key']))
                u['is_following'] = bool(cur.fetchone())

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
        result = []
        for r in rows:
            n = dict(r)
            ts = n.get('created_at')
            if ts:
                import datetime
                now = datetime.datetime.now(ts.tzinfo)
                age = int((now - ts).total_seconds())
                if age < 60:      n['time_ago'] = 'just now'
                elif age < 3600:  n['time_ago'] = f"{age // 60}m ago"
                elif age < 86400: n['time_ago'] = f"{age // 3600}h ago"
                elif age < 604800:n['time_ago'] = f"{age // 86400}d ago"
                else:             n['time_ago'] = f"{age // 604800}w ago"
            result.append(n)
        return {'status': 200, 'notifications': result}
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
            return {'status': 200, 'convo_key': row['convo_key']}
        convo_key = gen_key()
        cur.execute("INSERT INTO conversations (convo_key, user_a_key, user_b_key) VALUES (%s,%s,%s)",
                    (convo_key, user_key, other_key))
        conn.commit()
        cur.close()
        return {'status': 200, 'convo_key': convo_key}
    except Exception as e:
        conn.rollback()
        return {'status': 500, 'message': 'Could not create conversation.'}
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
    convo_res = get_or_create_conversation(user_key, recipient_key)
    convo_key = convo_res.get('convo_key') if isinstance(convo_res, dict) else convo_res
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
        result = []
        for r in reversed(rows):
            m = dict(r)
            ts = m.get('sent_at')
            if ts:
                import datetime
                now = datetime.datetime.now(ts.tzinfo)
                age = int((now - ts).total_seconds())
                if age < 60:      m['time_ago'] = 'just now'
                elif age < 3600:  m['time_ago'] = f"{age // 60}m ago"
                elif age < 86400: m['time_ago'] = f"{age // 3600}h ago"
                else:             m['time_ago'] = f"{age // 86400}d ago"
            result.append(m)
        return {'status': 200, 'messages': result}
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
    ans['user_key']    = user['user_key']
    ans['department']  = user.get('department', '')
    ans['university']  = user.get('university', '')

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
# Simple in-memory rate limiter
_rl = {}
def _rate_ok(key, limit=100, window=60):
    import time; now=time.time()
    _rl[key] = [t for t in _rl.get(key,[]) if now-t<window]
    if len(_rl[key])>=limit: return False
    _rl[key].append(now); return True

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
            # Increment failed attempt counter
            if _email_bf:
                try:
                    conn_fa = get_conn()
                    cur_fa = conn_fa.cursor(cursor_factory=RealDictCursor)
                    cur_fa.execute("SELECT failed_login_attempts FROM user_auth WHERE email=%s",(_email_bf,))
                    _uf = cur_fa.fetchone()
                    if _uf:
                        _attempts = (_uf.get('failed_login_attempts') or 0) + 1
                        if _attempts >= 5:
                            import datetime as _dbt2
                            _lock = _dbt2.datetime.utcnow() + _dbt2.timedelta(minutes=15)
                            cur_fa.execute("UPDATE user_auth SET failed_login_attempts=%s,locked_until=%s WHERE email=%s",(_attempts,_lock,_email_bf))
                        else:
                            cur_fa.execute("UPDATE user_auth SET failed_login_attempts=%s WHERE email=%s",(_attempts,_email_bf))
                        conn_fa.commit()
                    release_conn(conn_fa)
                except: pass
            return {'status': 400, 'message': msg_map.get(check.get('error'), A.Genericerror)}
        user_key = insert_user(x)
        new_token = create_session(user_key, x.get('device_info', ''))
        user      = get_user_by_key(user_key)
        ans       = {'status': 200, 'message': A.Successfulsignupmessage}
        ans      |= Frontend_personalizer(x, user, new_token)
        return ans

    # ── SIGNIN ────────────────────────────────────────────────
    elif status == 'signin':
        # Brute force protection
        _email_bf = x.get('email','').strip().lower()
        if _email_bf:
            conn_bf = get_conn()
            try:
                cur_bf = conn_bf.cursor(cursor_factory=RealDictCursor)
                cur_bf.execute("SELECT failed_login_attempts,locked_until FROM user_auth WHERE email=%s",(_email_bf,))
                _u_bf = cur_bf.fetchone()
                if _u_bf and _u_bf.get('locked_until'):
                    import datetime as _dbt
                    _lk = _u_bf['locked_until']
                    if hasattr(_lk,'replace'): _lk=_lk.replace(tzinfo=None)
                    if _dbt.datetime.utcnow() < _lk:
                        _mins = max(1, int((_lk-_dbt.datetime.utcnow()).total_seconds()//60)+1)
                        release_conn(conn_bf)
                        return {'status':429,'message':f'Too many failed attempts. Try again in {_mins} minute(s).'}
            finally:
                release_conn(conn_bf)
        check = verify_signin_data(x)
        if check['status'] != 200:
            msg_map = {
                'credentials': A.Invalidcredentialsmessage,
                'deactivated': A.Accountdeactivatedmessage,
            }
            # Increment failed attempt counter
            if _email_bf:
                try:
                    conn_fa = get_conn()
                    cur_fa = conn_fa.cursor(cursor_factory=RealDictCursor)
                    cur_fa.execute("SELECT failed_login_attempts FROM user_auth WHERE email=%s",(_email_bf,))
                    _uf = cur_fa.fetchone()
                    if _uf:
                        _attempts = (_uf.get('failed_login_attempts') or 0) + 1
                        if _attempts >= 5:
                            import datetime as _dbt2
                            _lock = _dbt2.datetime.utcnow() + _dbt2.timedelta(minutes=15)
                            cur_fa.execute("UPDATE user_auth SET failed_login_attempts=%s,locked_until=%s WHERE email=%s",(_attempts,_lock,_email_bf))
                        else:
                            cur_fa.execute("UPDATE user_auth SET failed_login_attempts=%s WHERE email=%s",(_attempts,_email_bf))
                        conn_fa.commit()
                    release_conn(conn_fa)
                except: pass
            return {'status': 400, 'message': msg_map.get(check.get('error'), A.Genericerror)}
        user_key  = check['user_key']
        new_token = create_session(user_key, x.get('device_info', ''))
        user      = get_user_by_key(user_key)
        update_last_seen(user_key)
        # Reset brute force counter on success
        try:
            conn_rs2 = get_conn()
            cur_rs2 = conn_rs2.cursor()
            cur_rs2.execute("UPDATE user_auth SET failed_login_attempts=0,locked_until=NULL WHERE user_key=%s",(user_key,))
            conn_rs2.commit()
            release_conn(conn_rs2)
        except: pass
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

    elif status == 'get_trending_hashtags':
        _htc = get_conn()
        try:
            import re as _re
            _htcc = _htc.cursor(cursor_factory=RealDictCursor)
            _htcc.execute("SELECT content FROM posts WHERE created_at>NOW()-INTERVAL '7 days' AND visibility='public' AND content LIKE '%#%' LIMIT 500")
            _htrows = _htcc.fetchall()
            _htags = {}
            for _htr in _htrows:
                for _t in _re.findall(r'#([A-Za-z0-9_]+)', _htr['content'] or ''):
                    _htags[_t.lower()] = _htags.get(_t.lower(),0)+1
            _htsorted = sorted(_htags.items(),key=lambda x:x[1],reverse=True)[:20]
            return {'status':200,'hashtags':[{'tag':t,'count':c} for t,c in _htsorted]}
        finally: release_conn(_htc)

    elif status == 'get_trending_topics':
        topics = get_trending_topics()
        return {'status': 200, 'trending_topics_html': build_trending_topics_html(topics)}

    # ── SOCIAL ────────────────────────────────────────────────
    elif status == 'toggle_like':     return toggle_like(x, token)
    elif status == 'post_comment':    return post_comment(x, token)
    elif status == 'get_comments':    return {'status': 200, 'comments': get_comments(x)}
    elif status == 'like_comment':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _clkey = x.get('comment_key')
        _clc = get_conn()
        try:
            _clcc = _clc.cursor(cursor_factory=RealDictCursor)
            _clcc.execute("SELECT 1 FROM comment_likes WHERE user_key=%s AND comment_key=%s",(user_key,_clkey))
            if _clcc.fetchone():
                _clcc.execute("DELETE FROM comment_likes WHERE user_key=%s AND comment_key=%s",(user_key,_clkey))
                _clcc.execute("UPDATE comments SET like_count=GREATEST(0,COALESCE(like_count,0)-1) WHERE comment_key=%s RETURNING like_count",(_clkey,))
                _claction='unliked'
            else:
                _clcc.execute("INSERT INTO comment_likes VALUES(%s,%s) ON CONFLICT DO NOTHING",(user_key,_clkey))
                _clcc.execute("UPDATE comments SET like_count=COALESCE(like_count,0)+1 WHERE comment_key=%s RETURNING like_count",(_clkey,))
                _claction='liked'
            _clr = _clcc.fetchone()
            _clc.commit()
            return {'status':200,'action':_claction,'like_count':_clr['like_count'] if _clr else 0}
        finally: release_conn(_clc)

    elif status == 'delete_comment':  return delete_comment(x, token)
    elif status == 'toggle_bookmark': return toggle_bookmark(x, token)
    elif status == 'toggle_follow':   return toggle_follow(x, token)
    elif status == 'report':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _rtype = x.get('target_type')
        _rkey  = x.get('target_key')
        _rreason = x.get('reason','Inappropriate content')
        if not _rtype or not _rkey: return {'status':400,'message':'Missing target'}
        _rc = get_conn()
        try:
            _rcc = _rc.cursor()
            _rcc.execute(
                "INSERT INTO reports(report_key,reporter_key,target_type,target_key,reason) VALUES(%s,%s,%s,%s,%s)",
                (gen_key(),user_key,_rtype,_rkey,_rreason)
            )
            _rc.commit()
            return {'status':200,'message':'Report submitted. We will review it.'}
        except: return {'status':500,'message':'Could not submit report'}
        finally: release_conn(_rc)

    elif status == 'toggle_mute':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _mtkey = x.get('target_key')
        _mtc = get_conn()
        try:
            _mtcc = _mtc.cursor()
            _mtcc.execute("SELECT 1 FROM mutes WHERE muter_key=%s AND muted_key=%s",(user_key,_mtkey))
            if _mtcc.fetchone():
                _mtcc.execute("DELETE FROM mutes WHERE muter_key=%s AND muted_key=%s",(user_key,_mtkey))
                _mta='unmuted'
            else:
                _mtcc.execute("INSERT INTO mutes(muter_key,muted_key) VALUES(%s,%s) ON CONFLICT DO NOTHING",(user_key,_mtkey))
                _mta='muted'
            _mtc.commit()
            return {'status':200,'action':_mta,'message':f'User {_mta}'}
        finally: release_conn(_mtc)

    elif status == 'toggle_block':    return toggle_block(x, token)
    elif status == 'vote_poll':       return vote_poll(x, token)
    elif status == 'rsvp_event':      return rsvp_event(x, token)
    elif status == 'apply_bounty':    return apply_bounty(x, token)

    # ── CREATE ────────────────────────────────────────────────
    elif status == 'create_post':  return create_post(x, token)
    elif status == 'edit_post':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _epostkey = x.get('post_key')
        _econtent = (x.get('content') or '').strip()
        if not _econtent: return {'status':400,'message':'Content cannot be empty'}
        _ec = get_conn()
        try:
            import datetime as _dt3
            _ecc = _ec.cursor(cursor_factory=RealDictCursor)
            _ecc.execute("SELECT user_key,created_at FROM posts WHERE post_key=%s",(_epostkey,))
            _ep = _ecc.fetchone()
            if not _ep: return {'status':404,'message':'Post not found'}
            if _ep['user_key']!=user_key: return {'status':403,'message':'Not your post'}
            _age = (_dt3.datetime.utcnow()-_ep['created_at'].replace(tzinfo=None)).total_seconds()
            if _age > 900: return {'status':400,'message':'Posts can only be edited within 15 minutes'}
            _ecc.execute("UPDATE posts SET content=%s,edited_at=NOW() WHERE post_key=%s",(_econtent,_epostkey))
            _ec.commit()
            return {'status':200,'message':'Post updated'}
        finally: release_conn(_ec)

    elif status == 'pin_post':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _ppkey = x.get('post_key')
        _pc = get_conn()
        try:
            _pcc = _pc.cursor(cursor_factory=RealDictCursor)
            _pcc.execute("SELECT user_key FROM posts WHERE post_key=%s",(_ppkey,))
            _pp = _pcc.fetchone()
            if not _pp or _pp['user_key']!=user_key: return {'status':403,'message':'Not your post'}
            _pcc.execute("UPDATE posts SET is_pinned=FALSE WHERE user_key=%s",(user_key,))
            _pcc.execute("UPDATE posts SET is_pinned=NOT COALESCE(is_pinned,FALSE) WHERE post_key=%s RETURNING is_pinned",(_ppkey,))
            _pr = _pcc.fetchone()
            _pc.commit()
            return {'status':200,'pinned': _pr['is_pinned'] if _pr else False}
        finally: release_conn(_pc)

    elif status == 'delete_post':  return delete_post(x, token)

    # ── PROFILE ───────────────────────────────────────────────
    elif status == 'personalize':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        user           = get_user_by_key(user_key)
        following_data = get_following(user_key)
        notif_count    = get_unread_notif_count(token)
        ans            = {'status': 200}
        ans           |= Frontend_personalizer(x, user, token)
        ans['userListContent'] = build_user_list_html(following_data, user_key)
        ans['notif_count']     = notif_count
        return ans

    elif status == 'get_profile':
        user_key = validate_session(token)
        if not user_key:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        user = get_user_by_key(user_key)
        return {
            'status':         200,
            'full_name':      user['full_name'],
            'username':       user['username'],
            'bio':            user.get('biodescription') or A.defaultbiodescription,
            'avatar':         user.get('profilepicurl') or A.defaultavatarurl,
            'department':     user.get('department', ''),
            'university':     user.get('university', ''),
            'academic_level': user.get('academic_level', ''),
            'following':      user.get('numberoffollowing', 0),
            'followers':      user.get('numberoffollowers', 0),
            'likes':          user.get('numberoflikes', 0),
            'posts':          user.get('numberofposts', 0),
        }

    elif status == 'get_global_research':
        seen_keys = x.get('seen_keys', [])
        posts     = get_global_research(seen_keys)
        return {'status': 200, 'posts': posts}

    elif status == 'get_or_create_conversation':
        other_key = x.get('other_key')
        user_key_val = validate_session(token)
        if not user_key_val:
            return {'status': 401, 'message': A.Unauthorizedmessage}
        res = get_or_create_conversation(user_key_val, other_key)
        return res
    elif status == 'get_announcements':
        anns = get_announcements()
        return {'status': 200, 'announcements': anns}
    elif status == 'get_post':
        user_key = validate_session(token)
        if not user_key: return {'status': 401, 'message': A.Unauthorizedmessage}
        post = get_post(x.get('post_key'), user_key)
        if not post: return {'status': 404, 'message': 'Post not found.'}
        return {'status': 200, 'post': post}
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
    elif status == 'delete_conversation':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _dck = x.get('conversation_key')
        _dcc = get_conn()
        try:
            _dccc = _dcc.cursor()
            _dccc.execute("SELECT 1 FROM conversations WHERE conversation_key=%s AND (user1_key=%s OR user2_key=%s)",(_dck,user_key,user_key))
            if not _dccc.fetchone(): return {'status':403,'message':'Not your conversation'}
            _dccc.execute("DELETE FROM messages WHERE conversation_key=%s",(_dck,))
            _dccc.execute("DELETE FROM conversations WHERE conversation_key=%s",(_dck,))
            _dcc.commit()
            return {'status':200,'message':'Conversation deleted'}
        finally: release_conn(_dcc)

    elif status == 'get_dm_messages':     return get_dm_messages(x, token)
    elif status == 'typing_ping':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conv_key = x.get('conversation_key')
        if conv_key:
            _tc = get_conn()
            try:
                _tcc = _tc.cursor()
                _tcc.execute("UPDATE conversations SET last_typing_key=%s,last_typing_at=NOW() WHERE conversation_key=%s",(user_key,conv_key))
                _tc.commit()
            except: pass
            finally: release_conn(_tc)
        return {'status':200}

    elif status == 'get_typing':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conv_key = x.get('conversation_key')
        if not conv_key: return {'status':200,'typing':False}
        _tc2 = get_conn()
        try:
            import datetime as _dt2
            _tcc2 = _tc2.cursor(cursor_factory=RealDictCursor)
            _tcc2.execute(
                "SELECT c.last_typing_key,c.last_typing_at,u.full_name FROM conversations c LEFT JOIN user_auth u ON u.user_key=c.last_typing_key WHERE c.conversation_key=%s",
                (conv_key,)
            )
            row = _tcc2.fetchone()
            if row and row['last_typing_key'] and row['last_typing_key']!=user_key and row['last_typing_at']:
                age = (_dt2.datetime.utcnow()-row['last_typing_at'].replace(tzinfo=None)).total_seconds()
                if age < 4:
                    return {'status':200,'typing':True,'name':row['full_name']}
            return {'status':200,'typing':False}
        finally: release_conn(_tc2)

    elif status == 'send_dm':             return send_dm(x, token)
    elif status == 'get_global_messages': return get_global_messages()
    elif status == 'send_global_message': return send_global_message(x, token)

    # ── UNKNOWN ───────────────────────────────────────────────
    elif status == 'request_password_reset':
        email = x.get('email','').strip().lower()
        if not email: return {'status':400,'message':'Email required'}
        conn_pr = get_conn()
        try:
            cur_pr = conn_pr.cursor(cursor_factory=RealDictCursor)
            cur_pr.execute("SELECT user_key FROM user_auth WHERE email=%s",(email,))
            user = cur_pr.fetchone()
            if not user: return {'status':404,'message':'No account with that email'}
            import random as _rand3, datetime as _dt4
            code  = str(_rand3.randint(100000,999999))
            token2 = gen_key()
            expires = _dt4.datetime.utcnow() + _dt4.timedelta(minutes=15)
            cur_pr.execute("INSERT INTO password_resets(token,user_key,code,expires_at) VALUES(%s,%s,%s,%s) ON CONFLICT(user_key) DO UPDATE SET token=%s,code=%s,expires_at=%s",(token2,user['user_key'],code,expires,token2,code,expires))
            conn_pr.commit()
            return {'status':200,'code':code,'token':token2,'message':'Reset code generated'}
        except Exception as ex: return {'status':500,'message':str(ex)}
        finally: release_conn(conn_pr)

    elif status == 'confirm_password_reset':
        _tok = x.get('token',''); _code = x.get('code',''); _np = x.get('new_password','')
        if len(_np)<8: return {'status':400,'message':'Password must be at least 8 characters'}
        conn_cp = get_conn()
        try:
            import datetime as _dt5, bcrypt as _bc2
            cur_cp = conn_cp.cursor(cursor_factory=RealDictCursor)
            cur_cp.execute("SELECT * FROM password_resets WHERE token=%s AND code=%s",(_tok,_code))
            row = cur_cp.fetchone()
            if not row: return {'status':400,'message':'Invalid or expired code'}
            if _dt5.datetime.utcnow() > row['expires_at'].replace(tzinfo=None): return {'status':400,'message':'Code expired'}
            hashed = _bc2.hashpw(_np.encode(),_bc2.gensalt()).decode()
            cur_cp.execute("UPDATE user_auth SET password_hash=%s WHERE user_key=%s",(hashed,row['user_key']))
            cur_cp.execute("DELETE FROM password_resets WHERE user_key=%s",(row['user_key'],))
            conn_cp.commit()
            return {'status':200,'message':'Password reset successfully'}
        finally: release_conn(conn_cp)

    elif status == 'verify_email':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        code = x.get('code','')
        conn_ve = get_conn()
        try:
            cur_ve = conn_ve.cursor(cursor_factory=RealDictCursor)
            cur_ve.execute("SELECT code FROM email_verifications WHERE user_key=%s",(user_key,))
            row = cur_ve.fetchone()
            if not row or row['code']!=code: return {'status':400,'message':'Invalid code'}
            cur_ve.execute("UPDATE user_auth SET is_verified=TRUE WHERE user_key=%s",(user_key,))
            cur_ve.execute("DELETE FROM email_verifications WHERE user_key=%s",(user_key,))
            conn_ve.commit()
            return {'status':200,'message':'Account verified!'}
        finally: release_conn(conn_ve)

    elif status == 'get_profile_by_username':
        uname = x.get('username','').strip()
        if not uname: return {'status':400,'message':'Username required'}
        conn_gu = get_conn()
        try:
            cur_gu = conn_gu.cursor(cursor_factory=RealDictCursor)
            cur_gu.execute("SELECT user_key FROM user_auth WHERE username=%s OR user_key=%s",(uname,uname))
            row = cur_gu.fetchone()
            return {'status':200,'user_key':row['user_key']} if row else {'status':404,'message':'User not found'}
        finally: release_conn(conn_gu)

    elif status == 'rsvp_event':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _pk = x.get('post_key')
        conn_rv = get_conn()
        try:
            cur_rv = conn_rv.cursor(cursor_factory=RealDictCursor)
            cur_rv.execute("SELECT 1 FROM post_applications WHERE post_key=%s AND applicant_key=%s AND note='rsvp'",(_pk,user_key))
            if cur_rv.fetchone():
                cur_rv.execute("DELETE FROM post_applications WHERE post_key=%s AND applicant_key=%s AND note='rsvp'",(_pk,user_key))
                action='not_going'
            else:
                cur_rv.execute("INSERT INTO post_applications(application_key,post_key,applicant_key,note,status) VALUES(%s,%s,%s,'rsvp','accepted') ON CONFLICT DO NOTHING",(gen_key(),_pk,user_key))
                action='going'
            conn_rv.commit()
            return {'status':200,'action':action}
        finally: release_conn(conn_rv)

    elif status == 'get_rsvps':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _pk = x.get('post_key')
        conn_gr = get_conn()
        try:
            cur_gr = conn_gr.cursor(cursor_factory=RealDictCursor)
            cur_gr.execute("SELECT u.full_name,u.username,u.profilepicurl,u.university FROM post_applications pa JOIN user_auth u ON u.user_key=pa.applicant_key WHERE pa.post_key=%s AND pa.note='rsvp'",(_pk,))
            rows = cur_gr.fetchall()
            return {'status':200,'attendees':[dict(r) for r in rows]}
        finally: release_conn(conn_gr)

    elif status == 'apply_to_post':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _pk = x.get('post_key'); _note = x.get('note','')
        conn_aj = get_conn()
        try:
            cur_aj = conn_aj.cursor()
            cur_aj.execute("SELECT 1 FROM post_applications WHERE post_key=%s AND applicant_key=%s AND note!='rsvp'",(_pk,user_key))
            if cur_aj.fetchone(): return {'status':400,'message':'You already applied'}
            cur_aj.execute("INSERT INTO post_applications(application_key,post_key,applicant_key,note,status) VALUES(%s,%s,%s,%s,'pending')",(gen_key(),_pk,user_key,_note))
            conn_aj.commit()
            return {'status':200,'message':'Application submitted!'}
        finally: release_conn(conn_aj)

    elif status == 'get_my_applications':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_ap = get_conn()
        try:
            cur_ap = conn_ap.cursor(cursor_factory=RealDictCursor)
            sql_ap = "SELECT pa.*,p.content,pe.data as extras,u.full_name as poster_name FROM post_applications pa JOIN posts p ON p.post_key=pa.post_key LEFT JOIN post_extras pe ON pe.post_key=pa.post_key LEFT JOIN user_auth u ON u.user_key=p.user_key WHERE pa.applicant_key=%s ORDER BY pa.created_at DESC"
            cur_ap.execute(sql_ap,(user_key,))
            rows = cur_ap.fetchall()
            return {'status':200,'applications':[dict(r) for r in rows]}
        finally: release_conn(conn_ap)

    elif status == 'get_post_applications':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _pk = x.get('post_key')
        conn_pa = get_conn()
        try:
            cur_pa = conn_pa.cursor(cursor_factory=RealDictCursor)
            cur_pa.execute("SELECT user_key FROM posts WHERE post_key=%s",(_pk,))
            owner = cur_pa.fetchone()
            if not owner or owner['user_key']!=user_key: return {'status':403,'message':'Not your post'}
            sql_pa = "SELECT pa.*,u.full_name,u.username,u.profilepicurl,u.department,u.university FROM post_applications pa JOIN user_auth u ON u.user_key=pa.applicant_key WHERE pa.post_key=%s ORDER BY pa.created_at DESC"
            cur_pa.execute(sql_pa,(_pk,))
            rows = cur_pa.fetchall()
            return {'status':200,'applications':[dict(r) for r in rows]}
        finally: release_conn(conn_pa)

    elif status == 'mark_sold':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _pk = x.get('post_key')
        conn_ms = get_conn()
        try:
            cur_ms = conn_ms.cursor(cursor_factory=RealDictCursor)
            cur_ms.execute("SELECT user_key FROM posts WHERE post_key=%s",(_pk,))
            post = cur_ms.fetchone()
            if not post or post['user_key']!=user_key: return {'status':403,'message':'Not your post'}
            cur_ms.execute("UPDATE posts SET show_in_feed=FALSE WHERE post_key=%s",(_pk,))
            conn_ms.commit()
            return {'status':200,'message':'Marked as sold'}
        finally: release_conn(conn_ms)

    elif status == 'get_my_data':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_gd = get_conn()
        try:
            cur_gd = conn_gd.cursor(cursor_factory=RealDictCursor)
            cur_gd.execute("SELECT full_name,username,email,bio,university,department,academic_level,created_at FROM user_auth WHERE user_key=%s",(user_key,))
            profile = cur_gd.fetchone()
            cur_gd.execute("SELECT post_key,post_type,content,created_at,like_count,comment_count,view_count FROM posts WHERE user_key=%s ORDER BY created_at DESC LIMIT 100",(user_key,))
            posts = cur_gd.fetchall()
            return {'status':200,'profile':dict(profile) if profile else {},'posts':[dict(p) for p in posts]}
        finally: release_conn(conn_gd)

    elif status == 'get_active_sessions':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_as = get_conn()
        try:
            cur_as = conn_as.cursor(cursor_factory=RealDictCursor)
            cur_as.execute("SELECT session_key,created_at,device_info FROM sessions WHERE user_key=%s ORDER BY created_at DESC LIMIT 10",(user_key,))
            rows = cur_as.fetchall()
            sessions = [{'session_key':r['session_key'],'device':r.get('device_info','Unknown'),'created_at':str(r['created_at'])[:16]} for r in rows]
            return {'status':200,'sessions':sessions}
        finally: release_conn(conn_as)

    elif status == 'revoke_session':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        _sk = x.get('session_key')
        conn_rs = get_conn()
        try:
            cur_rs = conn_rs.cursor()
            cur_rs.execute("DELETE FROM sessions WHERE session_key=%s AND user_key=%s",(_sk,user_key))
            conn_rs.commit()
            return {'status':200,'message':'Session revoked'}
        finally: release_conn(conn_rs)

    elif status == 'check_new_posts':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        latest_key = x.get('latest_key','')
        if not latest_key: return {'status':200,'new_count':0}
        conn_cn = get_conn()
        try:
            cur_cn = conn_cn.cursor(cursor_factory=RealDictCursor)
            cur_cn.execute("SELECT COUNT(*) as cnt FROM posts p WHERE p.post_key!=%s AND p.visibility='public' AND p.show_in_feed=TRUE AND p.created_at>(SELECT created_at FROM posts WHERE post_key=%s)",(latest_key,latest_key))
            row = cur_cn.fetchone()
            return {'status':200,'new_count':int(row['cnt']) if row else 0}
        except: return {'status':200,'new_count':0}
        finally: release_conn(conn_cn)

    elif status == 'ping_online':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_po = get_conn()
        try:
            cur_po = conn_po.cursor()
            cur_po.execute("UPDATE user_auth SET last_seen=NOW() WHERE user_key=%s",(user_key,))
            conn_po.commit()
        except: pass
        finally: release_conn(conn_po)
        return {'status':200}

    elif status == 'dismiss_notification':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        notif_key = x.get('notif_key')
        conn_dn = get_conn()
        try:
            cur_dn = conn_dn.cursor()
            cur_dn.execute("DELETE FROM notifications WHERE notification_key=%s AND recipient_key=%s",(notif_key,user_key))
            conn_dn.commit()
            return {'status':200}
        finally: release_conn(conn_dn)


    elif status == 'mark_dm_read':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        convo_key = x.get('convo_key')
        conn_mr = get_conn()
        try:
            cur_mr = conn_mr.cursor()
            cur_mr.execute("UPDATE messages SET read_at=NOW() WHERE conversation_key=%s AND sender_key!=%s AND read_at IS NULL",(convo_key, user_key))
            conn_mr.commit()
            return {'status':200}
        finally: release_conn(conn_mr)

    elif status == 'get_unread_dm_count':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_ud = get_conn()
        try:
            cur_ud = conn_ud.cursor(cursor_factory=RealDictCursor)
            cur_ud.execute("SELECT COUNT(*) as cnt FROM messages m JOIN conversations c ON c.conversation_key=m.conversation_key WHERE (c.user1_key=%s OR c.user2_key=%s) AND m.sender_key!=%s AND m.read_at IS NULL",(user_key,user_key,user_key))
            row = cur_ud.fetchone()
            return {'status':200,'count':int(row['cnt']) if row else 0}
        finally: release_conn(conn_ud)

    elif status == 'cancel_event':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        post_key = x.get('post_key'); reason = x.get('reason','Event has been cancelled')
        conn_ce = get_conn()
        try:
            cur_ce = conn_ce.cursor(cursor_factory=RealDictCursor)
            cur_ce.execute("SELECT user_key,content FROM posts WHERE post_key=%s AND post_type='event'",(post_key,))
            ev = cur_ce.fetchone()
            if not ev or ev['user_key']!=user_key: return {'status':403,'message':'Not your event'}
            cur_ce.execute("UPDATE posts SET show_in_feed=FALSE WHERE post_key=%s",(post_key,))
            cur_ce.execute("SELECT applicant_key FROM post_applications WHERE post_key=%s AND note='rsvp'",(post_key,))
            rsvps = cur_ce.fetchall()
            for r in rsvps:
                cur_ce.execute("INSERT INTO notifications(notification_key,recipient_key,sender_key,type,post_key,message,created_at) VALUES(%s,%s,%s,'event_cancelled',%s,%s,NOW())",(gen_key(),r['applicant_key'],user_key,post_key,f"Event cancelled: {reason}"))
            conn_ce.commit()
            return {'status':200,'notified':len(rsvps)}
        finally: release_conn(conn_ce)

    elif status == 'get_research_tags':
        conn_rt = get_conn()
        try:
            cur_rt = conn_rt.cursor(cursor_factory=RealDictCursor)
            cur_rt.execute("SELECT pe.data->>'tags' as tags FROM post_extras pe JOIN posts p ON p.post_key=pe.post_key WHERE p.post_type='research' AND pe.data->>'tags' IS NOT NULL ORDER BY p.created_at DESC LIMIT 200")
            rows = cur_rt.fetchall()
            from collections import Counter; import json
            all_tags = []
            for r in rows:
                try:
                    tags = json.loads(r['tags']) if isinstance(r['tags'],str) else r['tags']
                    if isinstance(tags,list): all_tags.extend(tags)
                except: pass
            top = Counter(all_tags).most_common(30)
            return {'status':200,'tags':[{'tag':t,'count':c} for t,c in top]}
        finally: release_conn(conn_rt)

    elif status == 'follow_research_tag':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        tag = x.get('tag','').strip().lower()
        if not tag: return {'status':400,'message':'Tag required'}
        conn_frt = get_conn()
        try:
            cur_frt = conn_frt.cursor()
            cur_frt.execute("SELECT 1 FROM user_tag_follows WHERE user_key=%s AND tag=%s",(user_key,tag))
            if cur_frt.fetchone():
                cur_frt.execute("DELETE FROM user_tag_follows WHERE user_key=%s AND tag=%s",(user_key,tag))
                action='unfollowed'
            else:
                cur_frt.execute("INSERT INTO user_tag_follows(user_key,tag,created_at) VALUES(%s,%s,NOW()) ON CONFLICT DO NOTHING",(user_key,tag))
                action='followed'
            conn_frt.commit()
            return {'status':200,'action':action}
        finally: release_conn(conn_frt)

    elif status == 'get_university_feed':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        conn_uf = get_conn()
        try:
            cur_uf = conn_uf.cursor(cursor_factory=RealDictCursor)
            cur_uf.execute("SELECT university,department FROM user_auth WHERE user_key=%s",(user_key,))
            me = cur_uf.fetchone()
            if not me or not me.get('university'): return {'status':400,'message':'No university set'}
            filter_type = x.get('filter','university')
            seen_keys = x.get('seen_keys',[]) or []
            if filter_type == 'department' and me.get('department'):
                cur_uf.execute("SELECT p.*,u.full_name,u.username,u.profilepicurl,u.account_level,u.department,u.university FROM posts p JOIN user_auth u ON u.user_key=p.user_key WHERE u.department=%s AND p.visibility='public' AND p.show_in_feed=TRUE AND p.post_key!=ALL(%s) ORDER BY p.created_at DESC LIMIT 20",(me['department'],seen_keys))
            else:
                cur_uf.execute("SELECT p.*,u.full_name,u.username,u.profilepicurl,u.account_level,u.department,u.university FROM posts p JOIN user_auth u ON u.user_key=p.user_key WHERE u.university=%s AND p.visibility='public' AND p.show_in_feed=TRUE AND p.post_key!=ALL(%s) ORDER BY p.created_at DESC LIMIT 20",(me['university'],seen_keys))
            posts = cur_uf.fetchall()
            return {'status':200,'posts':[dict(p) for p in posts],'university':me['university'],'department':me.get('department','')}
        finally: release_conn(conn_uf)

    elif status == 'expire_bounties':
        conn_eb = get_conn()
        try:
            cur_eb = conn_eb.cursor()
            cur_eb.execute("UPDATE posts SET show_in_feed=FALSE WHERE post_type='bounty' AND show_in_feed=TRUE AND post_key IN (SELECT post_key FROM post_extras WHERE (data->>'deadline') IS NOT NULL AND (data->>'deadline')::date < CURRENT_DATE)")
            conn_eb.commit()
            return {'status':200,'expired':cur_eb.rowcount}
        finally: release_conn(conn_eb)


    elif status == 'get_bounties':
        conn_gb = get_conn()
        try:
            cur_gb = conn_gb.cursor(cursor_factory=RealDictCursor)
            category  = x.get('category')
            seen_keys = x.get('seen_keys') or []
            if category:
                cur_gb.execute(
                    "SELECT p.*,u.full_name,u.username,u.profilepicurl,u.account_level FROM posts p JOIN user_auth u ON u.user_key=p.user_key LEFT JOIN post_extras pe ON pe.post_key=p.post_key WHERE p.post_type='bounty' AND p.show_in_feed=TRUE AND p.post_key!=ALL(%s) AND (pe.data->>'category')=%s ORDER BY p.created_at DESC LIMIT 20",
                    (seen_keys, category)
                )
            else:
                cur_gb.execute(
                    "SELECT p.*,u.full_name,u.username,u.profilepicurl,u.account_level FROM posts p JOIN user_auth u ON u.user_key=p.user_key WHERE p.post_type='bounty' AND p.show_in_feed=TRUE AND p.post_key!=ALL(%s) ORDER BY p.created_at DESC LIMIT 20",
                    (seen_keys,)
                )
            posts = cur_gb.fetchall()
            return {'status':200,'posts':[dict(p) for p in posts]}
        finally: release_conn(conn_gb)

    elif status == 'get_marketplace':
        conn_gm = get_conn()
        try:
            cur_gm = conn_gm.cursor(cursor_factory=RealDictCursor)
            category  = x.get('category')
            sort_by   = x.get('sort','recent')
            seen_keys = x.get('seen_keys') or []
            sort_col  = 'p.created_at DESC'
            if sort_by == 'price_asc':
                sort_col = "(pe.data->>'price')::numeric ASC NULLS LAST"
            elif sort_by == 'price_desc':
                sort_col = "(pe.data->>'price')::numeric DESC NULLS LAST"
            base_q = "SELECT p.*,u.full_name,u.username,u.profilepicurl,u.account_level,pe.data as extras FROM posts p JOIN user_auth u ON u.user_key=p.user_key LEFT JOIN post_extras pe ON pe.post_key=p.post_key WHERE p.post_type='product' AND p.show_in_feed=TRUE AND p.post_key!=ALL(%s)"
            if category:
                cur_gm.execute(base_q + " AND (pe.data->>'category')=%s ORDER BY " + sort_col + " LIMIT 30", (seen_keys, category))
            else:
                cur_gm.execute(base_q + " ORDER BY " + sort_col + " LIMIT 30", (seen_keys,))
            posts = cur_gm.fetchall()
            return {'status':200,'posts':[dict(p) for p in posts]}
        finally: release_conn(conn_gm)

    elif status == 'withdraw_application':
        user_key = validate_session(token)
        if not user_key: return {'status':401,'message':A.Unauthorizedmessage}
        post_key = x.get('post_key')
        conn_wa = get_conn()
        try:
            cur_wa = conn_wa.cursor()
            cur_wa.execute("DELETE FROM post_applications WHERE applicant_key=%s AND post_key=%s AND note!='rsvp'",(user_key,post_key))
            if cur_wa.rowcount == 0: return {'status':404,'message':'Application not found'}
            conn_wa.commit()
            return {'status':200,'message':'Application withdrawn'}
        finally: release_conn(conn_wa)


    elif status == 'forgot_password':
        email = x.get('email','').lower().strip()
        conn_fp = get_conn()
        try:
            cur_fp = conn_fp.cursor(cursor_factory=RealDictCursor)
            cur_fp.execute("SELECT user_key FROM user_auth WHERE email=%s", (email,))
            user = cur_fp.fetchone()
            if not user:
                return {'status':200,'message':'If that email exists, a reset link has been sent'}
            import secrets, datetime
            reset_token = secrets.token_urlsafe(32)
            expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            cur_fp.execute("UPDATE user_auth SET reset_token=%s, reset_token_expires=%s WHERE user_key=%s",(reset_token,expires,user['user_key']))
            conn_fp.commit()
            # In production: send email with reset link
            return {'status':200,'message':'Reset link sent'}
        finally: release_conn(conn_fp)

    else:
        return {'status': 400, 'message': A.Genericerror}


# ── Startup ───────────────────────────────────────────────────
#create_table()
