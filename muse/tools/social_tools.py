"""Social Media Tools — post CRUD, voice matching bridge, and hashtag generation.

Local-only mode: posts are drafted and stored in SQLite. The artist
copies the caption and posts manually on Instagram. ChromaDB is used
for RAG-based voice matching.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from muse.config import config
from muse.rag.voice_engine import VoiceEngine

logger = logging.getLogger(__name__)


# Genre-aware hashtag library for musicians
HASHTAG_LIBRARY = {
    "indie": ["#indiemusic", "#indieartist", "#indierock", "#indiefolk", "#indiepop",
              "#independentartist", "#indiemusician", "#supportindiemusic"],
    "rock": ["#rockmusic", "#liverock", "#rockband", "#alternativerock", "#rocknroll",
             "#rockshow", "#rocklife"],
    "hip hop": ["#hiphop", "#hiphopmusic", "#rapper", "#hiphopculture", "#bars",
                "#rapmusic", "#hiphoplife"],
    "r&b": ["#rnb", "#rnbmusic", "#rnbsinger", "#rnbsoul", "#contemporaryrnb",
             "#rnbvibes"],
    "jazz": ["#jazz", "#jazzmusic", "#jazzmusician", "#livejazz", "#jazzlife",
             "#jazzclub", "#smoothjazz"],
    "country": ["#countrymusic", "#countrysinger", "#countrysong", "#countrylife",
                "#countryartist", "#nashville"],
    "electronic": ["#electronicmusic", "#edm", "#producer", "#beats", "#synth",
                   "#electronica", "#dancemusic"],
    "soul": ["#soulmusic", "#soul", "#soulful", "#soulsinger", "#neosoul",
             "#soulartist"],
    "pop": ["#popmusic", "#popsinger", "#popartist", "#newpop", "#synthpop",
            "#dreampop"],
    "folk": ["#folkmusic", "#folkartist", "#folksinger", "#acoustic", "#folkrock",
             "#singersongwriter"],
    "general": ["#newmusic", "#livemusic", "#musician", "#musiclife", "#originalmusic",
                "#singersongwriter", "#musicislife", "#supportlocalmusic",
                "#independentmusician", "#musicianlife"],
    "gig": ["#liveshow", "#giglife", "#liveset", "#concert", "#tonightsshow",
            "#musicvenue", "#liveperformance", "#showtime"],
    "studio": ["#studiolife", "#recording", "#studioflow", "#newmusic",
               "#recordingstudio", "#tracking", "#mixing", "#inthe studio"],
    "release": ["#newsingle", "#newrelease", "#outnow", "#streamit", "#presave",
                "#newmusicalert", "#justdropped", "#linkinbio"],
    "behind the scenes": ["#bts", "#behindthescenes", "#behindthemusic",
                          "#studiovibes", "#theprocess", "#makingmusic"],
    "collaboration": ["#collab", "#collaboration", "#featurefriday", "#musiccollab",
                      "#workingwith"],
}


class SocialTools:
    """Social media post management with voice-matched caption generation."""

    def __init__(self):
        self.db_path = config.DB_PATH
        self.voice_engine = VoiceEngine()
        self._init_db()
        self._seed_sample_data()

    def _init_db(self) -> None:
        """Create the social_posts table if it doesn't exist."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS social_posts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL DEFAULT 'instagram',
                    post_type TEXT NOT NULL DEFAULT 'feed',
                    caption TEXT NOT NULL DEFAULT '',
                    hashtags TEXT NOT NULL DEFAULT '[]',
                    image_description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    scheduled_time TEXT,
                    voice_category TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _seed_sample_data(self) -> None:
        """Seed sample posts for testing/demo if none exist."""
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            count = conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0]
            if count > 0:
                return

            now = datetime.now().isoformat()
            sample_posts = [
                {
                    "id": f"post_{uuid.uuid4().hex[:8]}",
                    "platform": "instagram",
                    "post_type": "feed",
                    "caption": (
                        "This Saturday at The Earl. Doors at 8, we hit at 9:30. "
                        "Full band, new songs, and some surprises. "
                        "Don't sleep on this one Atlanta."
                    ),
                    "hashtags": json.dumps([
                        "#livemusic", "#atlantamusic", "#theearlatlanta",
                        "#liveshow", "#indierock", "#newmusic",
                    ]),
                    "image_description": "Band photo on stage at The Earl with purple lighting",
                    "status": "draft",
                    "voice_category": "gig_promo",
                    "notes": "For the March 22 show",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": f"post_{uuid.uuid4().hex[:8]}",
                    "platform": "instagram",
                    "post_type": "reel",
                    "caption": (
                        "3am vibes. When you finally nail that guitar tone you've "
                        "been chasing for two weeks. The process > the product. "
                        "New music coming very soon."
                    ),
                    "hashtags": json.dumps([
                        "#studiolife", "#recording", "#guitarlife",
                        "#behindthemusic", "#newmusic", "#theprocess",
                    ]),
                    "image_description": "Studio reel showing guitar recording at West End Sound",
                    "status": "draft",
                    "voice_category": "behind_the_scenes",
                    "notes": "West End Sound session reel",
                    "created_at": now,
                    "updated_at": now,
                },
            ]

            for post in sample_posts:
                conn.execute(
                    """INSERT INTO social_posts
                       (id, platform, post_type, caption, hashtags, image_description,
                        status, voice_category, notes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        post["id"], post["platform"], post["post_type"],
                        post["caption"], post["hashtags"], post["image_description"],
                        post["status"], post["voice_category"], post["notes"],
                        post["created_at"], post["updated_at"],
                    ),
                )
            conn.commit()
            logger.info(f"[SocialTools] Seeded {len(sample_posts)} sample posts")

    # ── Post CRUD ────────────────────────────────────────────────────

    def create_post_draft(
        self,
        caption: str,
        platform: str = "instagram",
        post_type: str = "feed",
        hashtags: list[str] | None = None,
        image_description: str = "",
        voice_category: str = "",
        notes: str = "",
    ) -> dict:
        """Create a new post draft.

        Args:
            caption: The post caption text.
            platform: Social media platform (default: instagram).
            post_type: Type of post (feed, reel, story, carousel).
            hashtags: List of hashtags.
            image_description: Description of the visual content.
            voice_category: Voice style category used.
            notes: Internal notes.

        Returns:
            Dict with the created post details.
        """
        post_id = f"post_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        hashtags_json = json.dumps(hashtags or [])

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute(
                """INSERT INTO social_posts
                   (id, platform, post_type, caption, hashtags, image_description,
                    status, voice_category, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
                (
                    post_id, platform, post_type, caption, hashtags_json,
                    image_description, voice_category, notes, now, now,
                ),
            )
            conn.commit()

        logger.info(f"[SocialTools] Created post draft {post_id}")

        return {
            "id": post_id,
            "platform": platform,
            "post_type": post_type,
            "caption": caption,
            "hashtags": hashtags or [],
            "image_description": image_description,
            "status": "draft",
            "voice_category": voice_category,
            "notes": notes,
            "created_at": now,
        }

    def list_posts(
        self,
        status: str | None = None,
        platform: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List posts with optional filters.

        Args:
            status: Filter by status (draft, scheduled, posted, archived).
            platform: Filter by platform.
            limit: Max number of posts to return.

        Returns:
            Dict with matching posts.
        """
        query = "SELECT * FROM social_posts WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if platform:
            query += " AND platform = ?"
            params.append(platform)

        # Exclude archived unless specifically requested
        if status != "archived":
            query += " AND status != 'archived'"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        posts = []
        for row in rows:
            posts.append({
                "id": row["id"],
                "platform": row["platform"],
                "post_type": row["post_type"],
                "caption_preview": (
                    row["caption"][:80] + "..."
                    if len(row["caption"]) > 80
                    else row["caption"]
                ),
                "status": row["status"],
                "hashtag_count": len(json.loads(row["hashtags"])),
                "voice_category": row["voice_category"] or "",
                "created_at": row["created_at"],
            })

        return {
            "total": len(posts),
            "posts": posts,
        }

    def get_post(self, post_id: str) -> dict:
        """Get full details of a specific post.

        Args:
            post_id: The post ID.

        Returns:
            Dict with full post details.
        """
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM social_posts WHERE id = ?", (post_id,)
            ).fetchone()

        if not row:
            return {"error": f"Post {post_id} not found"}

        return {
            "id": row["id"],
            "platform": row["platform"],
            "post_type": row["post_type"],
            "caption": row["caption"],
            "hashtags": json.loads(row["hashtags"]),
            "image_description": row["image_description"],
            "status": row["status"],
            "scheduled_time": row["scheduled_time"],
            "voice_category": row["voice_category"] or "",
            "notes": row["notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_post(self, post_id: str, updates: dict) -> dict:
        """Update fields on an existing post.

        Args:
            post_id: The post ID.
            updates: Key-value pairs of fields to update.

        Returns:
            Dict with updated post details.
        """
        allowed_fields = {
            "caption", "hashtags", "image_description", "status",
            "scheduled_time", "voice_category", "notes", "post_type",
        }

        valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        if not valid_updates:
            return {"error": f"No valid fields to update. Allowed: {allowed_fields}"}

        # Serialize hashtags if present
        if "hashtags" in valid_updates and isinstance(valid_updates["hashtags"], list):
            valid_updates["hashtags"] = json.dumps(valid_updates["hashtags"])

        valid_updates["updated_at"] = datetime.now().isoformat()

        set_clauses = ", ".join(f"{k} = ?" for k in valid_updates)
        values = list(valid_updates.values()) + [post_id]

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            result = conn.execute(
                f"UPDATE social_posts SET {set_clauses} WHERE id = ?",
                values,
            )
            conn.commit()

            if result.rowcount == 0:
                return {"error": f"Post {post_id} not found"}

        logger.info(f"[SocialTools] Updated post {post_id}: {list(valid_updates.keys())}")
        return self.get_post(post_id)

    def delete_post(self, post_id: str) -> dict:
        """Soft-delete a post by setting status to archived.

        Args:
            post_id: The post ID.

        Returns:
            Dict with confirmation.
        """
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            result = conn.execute(
                "UPDATE social_posts SET status = 'archived', updated_at = ? WHERE id = ?",
                (now, post_id),
            )
            conn.commit()

            if result.rowcount == 0:
                return {"error": f"Post {post_id} not found"}

        logger.info(f"[SocialTools] Archived post {post_id}")
        return {"archived": post_id, "message": "Post moved to archive"}

    # ── Voice Engine Bridge ──────────────────────────────────────────

    def get_voice_context(
        self,
        query: str,
        n_results: int = 3,
        category: str | None = None,
    ) -> dict:
        """Retrieve voice samples relevant to a query.

        Proxies to VoiceEngine.get_voice_context().
        """
        return self.voice_engine.get_voice_context(
            query=query,
            n_results=n_results,
            category=category,
        )

    def add_voice_sample(
        self,
        text: str,
        category: str = "other",
        source: str = "manual",
    ) -> dict:
        """Add a new voice sample for the artist.

        Proxies to VoiceEngine.add_sample().
        """
        return self.voice_engine.add_sample(
            text=text,
            category=category,
            source=source,
        )

    def list_voice_samples(self) -> dict:
        """List all stored voice samples.

        Proxies to VoiceEngine.list_samples().
        """
        return self.voice_engine.list_samples()

    # ── Hashtag Generation ───────────────────────────────────────────

    def generate_hashtags(
        self,
        topic: str,
        count: int = 15,
    ) -> dict:
        """Generate relevant hashtags for a topic.

        Combines genre-specific, topic-specific, and general music hashtags.

        Args:
            topic: The topic or context (e.g., "indie rock gig", "studio session").
            count: Number of hashtags to return.

        Returns:
            Dict with hashtag suggestions.
        """
        topic_lower = topic.lower()
        selected: list[str] = []

        # Match topic against hashtag categories
        for category, tags in HASHTAG_LIBRARY.items():
            if category in topic_lower:
                selected.extend(tags)

        # Always include general music hashtags
        selected.extend(HASHTAG_LIBRARY["general"])

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for tag in selected:
            if tag not in seen:
                seen.add(tag)
                unique.append(tag)

        # Trim to requested count
        hashtags = unique[:count]

        return {
            "topic": topic,
            "hashtags": hashtags,
            "count": len(hashtags),
            "tip": (
                "Use 20-30 hashtags for Instagram feed posts. "
                "Mix popular tags with niche ones for best reach. "
                "Put them in a comment or at the end of your caption."
            ),
        }
