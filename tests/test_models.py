"""Tests for Pydantic input models in server.py."""

import pytest
from pydantic import ValidationError

# Import models from server
import sys
sys.path.insert(0, "/Volumes/FS001/pythonscripts/moltbot")

from server import (
    SortOption,
    CommentSortOption,
    MoltbookRegisterInput,
    MoltbookBrowseFeedInput,
    MoltbookGetPostInput,
    MoltbookCreatePostInput,
    MoltbookCommentInput,
    MoltbookVoteInput,
    MoltbookListSubmoltsInput,
    MoltbookAgentStatusInput,
    MoltbookSearchSubmoltInput,
    MoltbookSubscribeInput,
    DEFAULT_FEED_LIMIT,
    MAX_FEED_LIMIT,
)


# ===========================================================================
# Enum tests
# ===========================================================================


class TestEnums:
    """Tests for sort option enums."""

    def test_sort_option_values(self):
        """SortOption should have expected values."""
        assert SortOption.HOT.value == "hot"
        assert SortOption.NEW.value == "new"
        assert SortOption.TOP.value == "top"
        assert SortOption.RISING.value == "rising"

    def test_comment_sort_option_values(self):
        """CommentSortOption should have expected values."""
        assert CommentSortOption.TOP.value == "top"
        assert CommentSortOption.NEW.value == "new"
        assert CommentSortOption.CONTROVERSIAL.value == "controversial"


# ===========================================================================
# MoltbookRegisterInput tests
# ===========================================================================


class TestMoltbookRegisterInput:
    """Tests for agent registration input model."""

    def test_valid_registration(self):
        """Valid registration data should pass."""
        model = MoltbookRegisterInput(
            name="TestAgent",
            description="A test agent for unit testing."
        )
        assert model.name == "TestAgent"
        assert model.description == "A test agent for unit testing."

    def test_whitespace_stripping(self):
        """Whitespace should be stripped from strings."""
        model = MoltbookRegisterInput(
            name="  TestAgent  ",
            description="  Description  "
        )
        assert model.name == "TestAgent"
        assert model.description == "Description"

    def test_name_too_long(self):
        """Name exceeding 64 chars should fail."""
        with pytest.raises(ValidationError) as exc_info:
            MoltbookRegisterInput(name="x" * 65, description="Valid")
        assert "string_too_long" in str(exc_info.value).lower()

    def test_description_too_long(self):
        """Description exceeding 500 chars should fail."""
        with pytest.raises(ValidationError) as exc_info:
            MoltbookRegisterInput(name="Valid", description="x" * 501)
        assert "string_too_long" in str(exc_info.value).lower()

    def test_extra_fields_forbidden(self):
        """Extra fields should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MoltbookRegisterInput(
                name="Test",
                description="Desc",
                extra_field="not allowed"
            )
        assert "extra" in str(exc_info.value).lower()


# ===========================================================================
# MoltbookBrowseFeedInput tests
# ===========================================================================


class TestMoltbookBrowseFeedInput:
    """Tests for feed browsing input model."""

    def test_defaults(self):
        """Default values should be applied."""
        model = MoltbookBrowseFeedInput()
        assert model.sort == SortOption.HOT
        assert model.limit == DEFAULT_FEED_LIMIT
        assert model.submolt is None

    def test_limit_bounds_min(self):
        """Limit below 1 should fail."""
        with pytest.raises(ValidationError):
            MoltbookBrowseFeedInput(limit=0)

    def test_limit_bounds_max(self):
        """Limit above MAX_FEED_LIMIT should fail."""
        with pytest.raises(ValidationError):
            MoltbookBrowseFeedInput(limit=MAX_FEED_LIMIT + 1)

    def test_valid_limit_at_max(self):
        """Limit at MAX_FEED_LIMIT should pass."""
        model = MoltbookBrowseFeedInput(limit=MAX_FEED_LIMIT)
        assert model.limit == MAX_FEED_LIMIT

    def test_submolt_filter(self):
        """Submolt filter should be accepted."""
        model = MoltbookBrowseFeedInput(submolt="aithoughts")
        assert model.submolt == "aithoughts"


# ===========================================================================
# MoltbookGetPostInput tests
# ===========================================================================


class TestMoltbookGetPostInput:
    """Tests for get post input model."""

    def test_valid_input(self):
        """Valid post ID should pass."""
        model = MoltbookGetPostInput(post_id="post_12345")
        assert model.post_id == "post_12345"
        assert model.comment_sort == CommentSortOption.TOP

    def test_empty_post_id_rejected(self):
        """Empty post ID should fail."""
        with pytest.raises(ValidationError):
            MoltbookGetPostInput(post_id="")

    def test_comment_sort_override(self):
        """Comment sort can be overridden."""
        model = MoltbookGetPostInput(
            post_id="post_123",
            comment_sort=CommentSortOption.NEW
        )
        assert model.comment_sort == CommentSortOption.NEW


# ===========================================================================
# MoltbookCreatePostInput tests
# ===========================================================================


class TestMoltbookCreatePostInput:
    """Tests for create post input model."""

    def test_text_post(self):
        """Text post with content should pass."""
        model = MoltbookCreatePostInput(
            title="My Post Title",
            content="Post body content here."
        )
        assert model.submolt == "general"  # default
        assert model.title == "My Post Title"
        assert model.content == "Post body content here."
        assert model.url is None

    def test_link_post(self):
        """Link post with URL should pass."""
        model = MoltbookCreatePostInput(
            title="Check this out",
            url="https://example.com/article"
        )
        assert model.url == "https://example.com/article"
        assert model.content is None

    def test_url_validation_http_rejected(self):
        """HTTP URLs should be rejected (HTTPS only)."""
        with pytest.raises(ValidationError):
            MoltbookCreatePostInput(
                title="Test",
                url="http://example.com"
            )

    def test_url_validation_invalid(self):
        """Invalid URLs should fail."""
        with pytest.raises(ValidationError) as exc_info:
            MoltbookCreatePostInput(
                title="Test",
                url="ftp://files.example.com"
            )
        assert "url must start with http" in str(exc_info.value).lower()

    def test_title_max_length(self):
        """Title exceeding 300 chars should fail."""
        with pytest.raises(ValidationError):
            MoltbookCreatePostInput(title="x" * 301)


# ===========================================================================
# MoltbookCommentInput tests
# ===========================================================================


class TestMoltbookCommentInput:
    """Tests for comment input model."""

    def test_valid_comment(self):
        """Valid comment should pass."""
        model = MoltbookCommentInput(
            post_id="post_123",
            content="This is my comment."
        )
        assert model.post_id == "post_123"
        assert model.content == "This is my comment."
        assert model.parent_id is None

    def test_reply_comment(self):
        """Reply to another comment should pass."""
        model = MoltbookCommentInput(
            post_id="post_123",
            content="Replying to you!",
            parent_id="comment_456"
        )
        assert model.parent_id == "comment_456"

    def test_content_max_length(self):
        """Content exceeding 10000 chars should fail."""
        with pytest.raises(ValidationError):
            MoltbookCommentInput(
                post_id="post_123",
                content="x" * 10001
            )


# ===========================================================================
# MoltbookVoteInput tests
# ===========================================================================


class TestMoltbookVoteInput:
    """Tests for vote input model."""

    def test_upvote_post(self):
        """Upvote on post should pass."""
        model = MoltbookVoteInput(
            target_id="post_123",
            target_type="post",
            direction="up"
        )
        assert model.target_type == "post"
        assert model.direction == "up"

    def test_downvote_comment(self):
        """Downvote on comment should pass."""
        model = MoltbookVoteInput(
            target_id="comment_456",
            target_type="comment",
            direction="down"
        )
        assert model.target_type == "comment"
        assert model.direction == "down"

    def test_invalid_target_type(self):
        """Invalid target type should fail."""
        with pytest.raises(ValidationError):
            MoltbookVoteInput(
                target_id="123",
                target_type="reply",  # invalid
                direction="up"
            )

    def test_invalid_direction(self):
        """Invalid direction should fail."""
        with pytest.raises(ValidationError):
            MoltbookVoteInput(
                target_id="123",
                target_type="post",
                direction="left"  # invalid
            )


# ===========================================================================
# MoltbookSubscribeInput tests
# ===========================================================================


class TestMoltbookSubscribeInput:
    """Tests for subscribe input model."""

    def test_subscribe(self):
        """Subscribe action should pass."""
        model = MoltbookSubscribeInput(
            submolt_name="aithoughts",
            action="subscribe"
        )
        assert model.submolt_name == "aithoughts"
        assert model.action == "subscribe"

    def test_unsubscribe(self):
        """Unsubscribe action should pass."""
        model = MoltbookSubscribeInput(
            submolt_name="general",
            action="unsubscribe"
        )
        assert model.action == "unsubscribe"

    def test_invalid_action(self):
        """Invalid action should fail."""
        with pytest.raises(ValidationError):
            MoltbookSubscribeInput(
                submolt_name="test",
                action="follow"  # invalid
            )


# ===========================================================================
# Empty input models tests
# ===========================================================================


class TestEmptyInputModels:
    """Tests for models that accept no parameters."""

    def test_list_submolts_input(self):
        """ListSubmoltsInput should accept no args."""
        model = MoltbookListSubmoltsInput()
        assert model is not None

    def test_agent_status_input(self):
        """AgentStatusInput should accept no args."""
        model = MoltbookAgentStatusInput()
        assert model is not None

    def test_search_submolt_input(self):
        """SearchSubmoltInput requires submolt_name."""
        model = MoltbookSearchSubmoltInput(submolt_name="general")
        assert model.submolt_name == "general"
