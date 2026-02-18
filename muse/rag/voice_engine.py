"""Voice Engine — ChromaDB-based RAG for matching the artist's writing voice.

Stores samples of how the artist writes captions and social media posts,
then retrieves the most relevant samples when generating new content so
Claude can match their tone and style.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

import chromadb

from muse.config import config
from muse.utils.env import is_cloud

logger = logging.getLogger(__name__)


# Seed voice samples — representative of common musician post styles
SEED_VOICE_SAMPLES = [
    {
        "text": (
            "ATLANTA. This Saturday. The Earl. Doors at 8, we hit at 9:30. "
            "Bringing the full band and some new joints we've been cooking up "
            "in the studio. Come early, it's gonna be packed. Link in bio for tix."
        ),
        "category": "gig_promo",
        "source": "seed",
    },
    {
        "text": (
            "3am in the studio and this track just clicked. Been chasing this "
            "sound for weeks and tonight it all came together. Can't wait for "
            "y'all to hear what we've been working on. The process is everything."
        ),
        "category": "behind_the_scenes",
        "source": "seed",
    },
    {
        "text": (
            "Last night was unreal. Sold out room, everyone singing along, "
            "pure energy from start to finish. This is why we do it. Thank you "
            "Atlanta for always showing up. Y'all are family."
        ),
        "category": "fan_engagement",
        "source": "seed",
    },
    {
        "text": (
            "It's here. New single drops this Friday at midnight. This one's "
            "personal — wrote it after a late night drive through the city. "
            "Pre-save link in bio. Let me know what you think when it hits."
        ),
        "category": "new_release",
        "source": "seed",
    },
    {
        "text": (
            "Huge shoutout to @miles_westendsound for the incredible mix on this "
            "one. When you work with people who get your vision, magic happens. "
            "Go check out his work. More collabs coming soon."
        ),
        "category": "collaboration",
        "source": "seed",
    },
]


class VoiceEngine:
    """ChromaDB-powered voice matching engine.

    Stores artist voice samples and retrieves the most relevant ones
    for a given query using semantic similarity search.
    """

    def __init__(self, persist_dir: str | None = None):
        self.persist_dir = persist_dir or config.CHROMADB_PATH
        self.collection_name = "artist_voice_samples"

        # Initialize ChromaDB — in-memory on cloud, persistent locally
        if is_cloud():
            self.client = chromadb.Client()
            logger.info("[VoiceEngine] Using in-memory ChromaDB (cloud mode)")
        else:
            try:
                self.client = chromadb.PersistentClient(path=self.persist_dir)
                logger.info(f"[VoiceEngine] Using persistent ChromaDB at {self.persist_dir}")
            except Exception as e:
                logger.warning(f"[VoiceEngine] PersistentClient failed ({e}), falling back to in-memory")
                self.client = chromadb.Client()

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Artist voice samples for caption generation"},
        )

        # Seed if empty
        if self.collection.count() == 0:
            self._seed_samples()

        logger.info(
            f"[VoiceEngine] Initialized with {self.collection.count()} voice samples"
        )

    def _seed_samples(self) -> None:
        """Seed the collection with representative voice samples."""
        logger.info("[VoiceEngine] Seeding voice samples...")

        ids = []
        documents = []
        metadatas = []

        for sample in SEED_VOICE_SAMPLES:
            sample_id = f"seed_{uuid.uuid4().hex[:8]}"
            ids.append(sample_id)
            documents.append(sample["text"])
            metadatas.append({
                "category": sample["category"],
                "source": sample["source"],
                "created_at": datetime.now().isoformat(),
            })

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"[VoiceEngine] Seeded {len(ids)} voice samples")

    def add_sample(
        self,
        text: str,
        category: str = "other",
        source: str = "manual",
    ) -> dict:
        """Add a new voice sample to the collection.

        Args:
            text: The sample text in the artist's voice.
            category: Voice category (gig_promo, behind_the_scenes, etc.).
            source: Where the sample came from.

        Returns:
            Dict with sample ID and confirmation.
        """
        sample_id = f"voice_{uuid.uuid4().hex[:8]}"

        self.collection.add(
            ids=[sample_id],
            documents=[text],
            metadatas=[{
                "category": category,
                "source": source,
                "created_at": datetime.now().isoformat(),
            }],
        )

        logger.info(f"[VoiceEngine] Added voice sample {sample_id} ({category})")
        return {
            "id": sample_id,
            "category": category,
            "text_preview": text[:100] + "..." if len(text) > 100 else text,
            "total_samples": self.collection.count(),
        }

    def get_voice_context(
        self,
        query: str,
        n_results: int = 3,
        category: str | None = None,
    ) -> dict:
        """Retrieve voice samples most relevant to a query.

        Args:
            query: The topic or context for the post being created.
            n_results: Number of samples to return.
            category: Optional category filter.

        Returns:
            Dict with matching voice samples for Claude to reference.
        """
        where_filter = {"category": category} if category else None

        # Ensure we don't request more than we have
        available = self.collection.count()
        n_results = min(n_results, available) if available > 0 else 1

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )
        except Exception as e:
            logger.warning(f"[VoiceEngine] Query failed with filter, retrying without: {e}")
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
            )

        samples = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                samples.append({
                    "text": doc,
                    "category": metadata.get("category", "unknown"),
                    "relevance_score": round(1 - (distance or 0), 3),
                })

        return {
            "query": query,
            "samples_found": len(samples),
            "voice_samples": samples,
            "instruction": (
                "Use these samples as reference for the artist's tone and style. "
                "Match their voice — their energy, vocabulary, and personality — "
                "but create original content. Don't copy the samples directly."
            ),
        }

    def list_samples(self) -> dict:
        """List all voice samples in the collection.

        Returns:
            Dict with all samples and their metadata.
        """
        results = self.collection.get()

        samples = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                samples.append({
                    "id": results["ids"][i],
                    "text_preview": doc[:80] + "..." if len(doc) > 80 else doc,
                    "category": metadata.get("category", "unknown"),
                    "source": metadata.get("source", "unknown"),
                    "created_at": metadata.get("created_at", ""),
                })

        return {
            "total_samples": len(samples),
            "samples": samples,
        }

    def delete_sample(self, sample_id: str) -> dict:
        """Remove a voice sample from the collection.

        Args:
            sample_id: The ID of the sample to delete.

        Returns:
            Dict with confirmation.
        """
        try:
            self.collection.delete(ids=[sample_id])
            logger.info(f"[VoiceEngine] Deleted voice sample {sample_id}")
            return {
                "deleted": sample_id,
                "remaining_samples": self.collection.count(),
            }
        except Exception as e:
            logger.error(f"[VoiceEngine] Error deleting sample {sample_id}: {e}")
            return {"error": f"Could not delete sample {sample_id}: {str(e)}"}

    def sample_count(self) -> int:
        """Return total number of voice samples."""
        return self.collection.count()
