def test_create_and_get_draft(social):
    post = social.create_post_draft(caption="Friday. Terminal West.", post_type="reel",
                                    hashtags=["#livemusic"])
    assert post["status"] == "draft"
    stored = social.get_post(post["id"])
    assert stored["caption"] == "Friday. Terminal West."
    assert stored["post_type"] == "reel"
    assert stored["hashtags"] == ["#livemusic"]


def test_list_filters_by_status(social):
    social.create_post_draft(caption="x", post_type="feed")
    drafts = social.list_posts(status="draft")["posts"]
    assert drafts and all(p["status"] == "draft" for p in drafts)


def test_update_post(social):
    post = social.create_post_draft(caption="old", post_type="feed")
    updated = social.update_post(post["id"], {"caption": "new", "hashtags": ["#a"], "id": "hijack"})
    assert updated["caption"] == "new"
    assert updated["hashtags"] == ["#a"]
    assert "error" in social.update_post(post["id"], {"id": "hijack"})


def test_delete_archives(social):
    post = social.create_post_draft(caption="x", post_type="feed")
    social.delete_post(post["id"])
    assert social.get_post(post["id"])["status"] == "archived"


def test_missing_post_is_an_error(social):
    assert "error" in social.get_post("post_nope")
    assert "error" in social.update_post("post_nope", {"caption": "x"})
    assert "error" in social.delete_post("post_nope")


def test_voice_library_seeded_and_extendable(social):
    before = social.list_voice_samples()["total_samples"]
    assert before == 5
    social.add_voice_sample("Late night in the studio again.", "behind_the_scenes")
    assert social.list_voice_samples()["total_samples"] == before + 1


def test_voice_context_returns_relevant_samples(social):
    context = social.get_voice_context("studio late night track", n_results=2)
    assert context["samples_found"] == 2
    assert all("text" in s for s in context["voice_samples"])


def test_voice_context_filters_by_category(social):
    context = social.get_voice_context("show", n_results=3, category="gig_promo")
    assert context["voice_samples"]
    assert all(s.get("category") == "gig_promo" for s in context["voice_samples"])


def test_generate_hashtags_count(social):
    result = social.generate_hashtags("live show atlanta", count=5)
    assert len(result["hashtags"]) == 5
    assert all(h.startswith("#") for h in result["hashtags"])
