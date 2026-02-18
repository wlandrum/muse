"""Data models for Muse social media operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PostType(str, Enum):
    FEED = "feed"
    REEL = "reel"
    STORY = "story"
    CAROUSEL = "carousel"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    ARCHIVED = "archived"


class VoiceCategory(str, Enum):
    GIG_PROMO = "gig_promo"
    BEHIND_THE_SCENES = "behind_the_scenes"
    FAN_ENGAGEMENT = "fan_engagement"
    NEW_RELEASE = "new_release"
    PERSONAL = "personal"
    COLLABORATION = "collaboration"
    MILESTONE = "milestone"
    OTHER = "other"


class SocialPost(BaseModel):
    """Represents a social media post draft."""

    id: Optional[str] = None
    platform: str = Field(default="instagram", description="Social media platform")
    post_type: PostType = Field(default=PostType.FEED, description="Type of post")
    caption: str = Field(default="", description="Post caption text")
    hashtags: list[str] = Field(default_factory=list, description="Hashtags for the post")
    image_description: str = Field(
        default="", description="Description of the image/visual content"
    )
    status: PostStatus = Field(default=PostStatus.DRAFT, description="Post status")
    scheduled_time: Optional[datetime] = Field(
        default=None, description="When to post (for scheduling)"
    )
    voice_category: Optional[VoiceCategory] = Field(
        default=None, description="Voice style category used"
    )
    notes: str = Field(default="", description="Internal notes about the post")
    created_at: Optional[datetime] = Field(default=None, description="When draft was created")
    updated_at: Optional[datetime] = Field(default=None, description="Last update time")

    def to_preview(self) -> str:
        """Format post draft for artist review."""
        type_emoji = {
            PostType.FEED: "📸",
            PostType.REEL: "🎬",
            PostType.STORY: "📱",
            PostType.CAROUSEL: "🎠",
        }.get(self.post_type, "📱")

        status_emoji = {
            PostStatus.DRAFT: "📝",
            PostStatus.SCHEDULED: "⏰",
            PostStatus.POSTED: "✅",
            PostStatus.ARCHIVED: "📦",
        }.get(self.status, "📝")

        lines = [
            f"--- {type_emoji} {self.platform.upper()} POST DRAFT ---",
            f"  Status: {status_emoji} {self.status.value.upper()}",
            f"  Type: {self.post_type.value.title()}",
        ]

        if self.image_description:
            lines.append(f"  Visual: {self.image_description}")

        lines.append(f"\n  Caption:\n  {self.caption}")

        if self.hashtags:
            lines.append(f"\n  Hashtags: {' '.join(self.hashtags)}")

        if self.voice_category:
            lines.append(f"\n  Voice Style: {self.voice_category.value.replace('_', ' ').title()}")

        if self.scheduled_time:
            lines.append(
                f"  Scheduled: {self.scheduled_time.strftime('%A, %B %d at %I:%M %p')}"
            )

        if self.notes:
            lines.append(f"  Notes: {self.notes}")

        lines.append("  --- END DRAFT ---")
        lines.append("\n  Tell me to edit it, or copy the caption to post on Instagram.")

        return "\n".join(lines)


class VoiceSample(BaseModel):
    """A sample of the artist's writing voice for RAG matching."""

    id: Optional[str] = None
    text: str = Field(description="The sample text in the artist's voice")
    category: VoiceCategory = Field(description="Category of content")
    source: str = Field(
        default="manual", description="Where the sample came from (manual, imported, etc.)"
    )
    created_at: Optional[datetime] = Field(default=None, description="When sample was added")
