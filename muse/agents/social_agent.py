"""Social Media Agent — handles Instagram content creation with RAG-based voice matching."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from muse.agents.base import BaseAgent
from muse.config import config
from muse.tools.social_tools import SocialTools

logger = logging.getLogger(__name__)


SOCIAL_SYSTEM_PROMPT = f"""You are the Social Media Agent for Muse, an AI manager for independent musicians.

Your job is to help the artist create compelling Instagram content that sounds authentically like them — not like a generic AI. You do this using voice matching: before writing any caption, you ALWAYS retrieve the artist's voice samples to match their tone.

The artist's name is {config.ARTIST_NAME}. The platform is Instagram.

## How You Operate

### Voice Matching (CRITICAL)
**ALWAYS call `get_voice_context` BEFORE writing any caption or post.** This retrieves samples of how the artist actually writes. Study the samples' energy, vocabulary, sentence structure, and personality. Then write NEW content that sounds like the artist wrote it — not a copy, but in their voice.

### Instagram Best Practices
- **Feed posts**: 150-300 words for captions. First line is the hook — make it grab attention. Use line breaks for readability.
- **Reels**: Short, punchy captions (1-3 sentences). Let the video do the talking.
- **Stories**: Minimal text. Direct, casual, immediate.
- **Carousels**: Tell a story across slides. Caption should add context the slides don't cover.
- **Hashtags**: 20-30 per feed post. Mix popular (100K+ posts) with niche (10K-100K). Put in a comment or at the end.
- **Posting times**: Generally best at 11am-1pm and 7pm-9pm local time.

### Music-Specific Content Ideas
- **Gig promos**: Build hype, include essential info (venue, date, time, ticket link), create urgency
- **Behind the scenes**: Studio sessions, rehearsals, songwriting process — fans love the creative journey
- **Fan engagement**: Thank-you posts after shows, Q&As, polls, "what should I play next?"
- **New releases**: Teaser rollout (behind-the-scenes → snippet → release day → thank you)
- **Collaborations**: Tag everyone involved, tell the story of how it happened
- **Milestones**: Streaming numbers, sold-out shows, anniversaries — celebrate with fans

## Rules

1. **ALWAYS call get_voice_context first** — before writing any caption. This is non-negotiable.
2. **Draft first, never auto-post** — always show the draft and let the artist approve or edit.
3. **Sound like the artist** — use their vocabulary, energy, and personality from the voice samples.
4. **Be concise** — musicians are busy. Don't over-explain your suggestions.
5. **Include hashtags** — generate relevant ones using the generate_hashtags tool.
6. **Image descriptions matter** — help the artist think about what visual to pair with the caption.
7. When the artist shares something they've written (a caption, a tweet, etc.), offer to add it as a voice sample.

## Important

- Today's date is {datetime.now().strftime("%A, %B %d, %Y")}.
- The artist's name is {config.ARTIST_NAME}.
- Platform: Instagram (local drafts only — the artist posts manually).
- All posts start as DRAFTS. The artist copies the caption to post on Instagram.
"""


TOOL_DEFINITIONS = [
    {
        "name": "get_voice_context",
        "description": (
            "MUST be called before writing any caption. Retrieves the artist's voice samples "
            "that are most relevant to the topic, so you can match their writing style."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "What the post is about — e.g. 'gig promotion at The Earl this Saturday', "
                        "'studio session behind the scenes', 'new single release'"
                    ),
                },
                "n_results": {
                    "type": "integer",
                    "description": "Number of voice samples to retrieve (default: 3)",
                    "default": 3,
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional filter: gig_promo, behind_the_scenes, fan_engagement, "
                        "new_release, personal, collaboration, milestone, other"
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_post_draft",
        "description": (
            "Create a new post draft. Always show the preview to the artist "
            "before considering it final."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "The post caption text, written in the artist's voice",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform (default: instagram)",
                    "default": "instagram",
                },
                "post_type": {
                    "type": "string",
                    "enum": ["feed", "reel", "story", "carousel"],
                    "description": "Type of Instagram post",
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of hashtags (include the # symbol)",
                },
                "image_description": {
                    "type": "string",
                    "description": "Description of the image/visual to pair with the post",
                },
                "voice_category": {
                    "type": "string",
                    "description": "Voice style category used for this post",
                },
                "notes": {
                    "type": "string",
                    "description": "Internal notes about the post",
                },
            },
            "required": ["caption", "post_type"],
        },
    },
    {
        "name": "list_posts",
        "description": "List the artist's post drafts, optionally filtered by status or platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["draft", "scheduled", "posted", "archived"],
                    "description": "Filter by post status. Optional.",
                },
                "platform": {
                    "type": "string",
                    "description": "Filter by platform. Optional.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max posts to return (default: 20)",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_post",
        "description": "Get full details of a specific post including caption, hashtags, and metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "The ID of the post to retrieve",
                },
            },
            "required": ["post_id"],
        },
    },
    {
        "name": "update_post",
        "description": (
            "Update fields on an existing post draft. Can change caption, hashtags, "
            "image description, status, notes, or post type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "The ID of the post to update",
                },
                "updates": {
                    "type": "object",
                    "description": (
                        "Key-value pairs of fields to update. Allowed fields: "
                        "caption, hashtags, image_description, status, "
                        "scheduled_time, voice_category, notes, post_type."
                    ),
                },
            },
            "required": ["post_id", "updates"],
        },
    },
    {
        "name": "delete_post",
        "description": "Archive a post draft (soft delete — moves to archived status).",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "The ID of the post to archive",
                },
            },
            "required": ["post_id"],
        },
    },
    {
        "name": "add_voice_sample",
        "description": (
            "Add a new voice sample to the artist's voice library. Use this when "
            "the artist shares something they've written that captures their voice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text in the artist's voice to store as a sample",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "gig_promo", "behind_the_scenes", "fan_engagement",
                        "new_release", "personal", "collaboration", "milestone", "other",
                    ],
                    "description": "Category of content",
                },
                "source": {
                    "type": "string",
                    "description": "Where the sample came from (e.g., 'artist_input', 'instagram', 'approved_draft')",
                },
            },
            "required": ["text", "category"],
        },
    },
    {
        "name": "list_voice_samples",
        "description": "List all stored voice samples in the artist's voice library.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "generate_hashtags",
        "description": (
            "Generate relevant hashtags for a topic. Combines genre-specific, "
            "topic-specific, and general music hashtags."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "The topic or context — e.g. 'indie rock gig', "
                        "'studio session', 'new single release'"
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "Number of hashtags to generate (default: 15)",
                    "default": 15,
                },
            },
            "required": ["topic"],
        },
    },
]


class SocialAgent(BaseAgent):
    """Manages social media — caption generation, voice matching, post drafting."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.social = SocialTools()

    @property
    def name(self) -> str:
        return "SocialAgent"

    def system_prompt(self) -> str:
        return SOCIAL_SYSTEM_PROMPT

    def tool_definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route tool calls to SocialTools methods."""

        if tool_name == "get_voice_context":
            return self.social.get_voice_context(
                query=tool_input["query"],
                n_results=tool_input.get("n_results", 3),
                category=tool_input.get("category"),
            )

        elif tool_name == "create_post_draft":
            return self.social.create_post_draft(
                caption=tool_input["caption"],
                platform=tool_input.get("platform", "instagram"),
                post_type=tool_input.get("post_type", "feed"),
                hashtags=tool_input.get("hashtags"),
                image_description=tool_input.get("image_description", ""),
                voice_category=tool_input.get("voice_category", ""),
                notes=tool_input.get("notes", ""),
            )

        elif tool_name == "list_posts":
            return self.social.list_posts(
                status=tool_input.get("status"),
                platform=tool_input.get("platform"),
                limit=tool_input.get("limit", 20),
            )

        elif tool_name == "get_post":
            return self.social.get_post(
                post_id=tool_input["post_id"],
            )

        elif tool_name == "update_post":
            return self.social.update_post(
                post_id=tool_input["post_id"],
                updates=tool_input["updates"],
            )

        elif tool_name == "delete_post":
            return self.social.delete_post(
                post_id=tool_input["post_id"],
            )

        elif tool_name == "add_voice_sample":
            return self.social.add_voice_sample(
                text=tool_input["text"],
                category=tool_input.get("category", "other"),
                source=tool_input.get("source", "manual"),
            )

        elif tool_name == "list_voice_samples":
            return self.social.list_voice_samples()

        elif tool_name == "generate_hashtags":
            return self.social.generate_hashtags(
                topic=tool_input["topic"],
                count=tool_input.get("count", 15),
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}
