import logging
import os
import re
import yaml
import setup
import pytest
import shutil

from selenium import webdriver
from unittest import TestCase
from unittest.mock import MagicMock, patch
from unittest.mock import PropertyMock

from diffengine import (
    init,
    Feed,
    EntryVersion,
    Entry,
    FeedEntry,
    home_path,
    load_config,
    setup_browser,
    UnknownWebdriverError,
    process_entry,
    UA,
    TwitterHandler,
    SendgridHandler,
    _fingerprint,
)
from diffengine.text_builder import build_text
from diffengine.utils import generate_config
from exceptions.sendgrid import (
    SendgridConfigNotFoundError,
    AlreadyEmailedError,
    SendgridArchiveUrlNotFoundError,
)
from exceptions.twitter import (
    TwitterConfigNotFoundError,
    TokenNotFoundError,
    AlreadyTweetedError,
    TwitterAchiveUrlNotFoundError,
    UpdateStatusError,
)

test_home = "test"

if os.path.isdir(test_home):
    shutil.rmtree(test_home)

# the sequence of these tests is significant


def test_version():
    assert setup.version in UA


def test_fingerprint():
    assert _fingerprint("foo bar") == "foobar"
    assert _fingerprint("foo bar\nbaz") == "foobarbaz"
    assert _fingerprint("foo<br>bar") == "foobar"
    assert _fingerprint("foo'bar") == "foobar"
    assert _fingerprint("foo’bar") == "foobar"


class FeedTest(TestCase):
    feed = None
    entry = None
    version = None

    def setUp(self) -> None:
        generate_config(test_home, {"db": "sqlite:///:memory:"})
        # set things up but disable prompting for initial feed
        init(test_home, prompt=False)
        self.feed = Feed.create(name="Test", url="https://inkdroid.org/feed.xml")
        self.feed.get_latest()
        self.entry = self.feed.entries[0]
        self.version = self.entry.get_latest()

    def test_feed(self):
        assert self.feed.created
        assert len(self.feed.entries) == 10

    def test_entry(self):
        assert type(self.version) == EntryVersion
        assert len(self.entry.versions) == 1

    def test_diff(self):
        e = self.entry
        v1 = e.versions[0]

        # remove some characters from the version
        v1.summary = v1.summary[0:-20]
        v1.save()

        v2 = e.get_latest()
        assert type(v2) == EntryVersion
        assert v2.diff
        assert v2.archive_url is not None
        assert (
            re.match("^https://web.archive.org/web/[0-9]+/.+$", v2.archive_url)
            is not None
        )

        diff = v2.diff
        assert diff.old == v1
        assert diff.new == v2
        assert os.path.isfile(diff.html_path)
        assert os.path.isfile(diff.screenshot_path)
        assert os.path.isfile(diff.thumbnail_path)

        # check that the url for the internet archive diff is working
        assert re.match(
            "^https://web.archive.org/web/diff/\\d+/\\d+/https.+$", diff.url
        )

    def test_html_diff(self):
        e = self.entry

        # add a change to the summary that htmldiff ignores
        v1 = e.versions[-1]
        parts = v1.summary.split()
        parts.insert(2, "<br>   \n")
        v1.summary = " ".join(parts)
        v1.save()

        v2 = e.get_latest()
        assert v2 is None

    def test_many_to_many(self):

        # these two feeds share this entry, we want diffengine to support
        # multiple feeds for the same content, which is fairly common at
        # large media organizations with multiple topical feeds
        url = "https://www.washingtonpost.com/classic-apps/how-a-week-of-tweets-by-trump-stoked-anxiety-moved-markets-and-altered-plans/2017/01/07/38be8e64-d436-11e6-9cb0-54ab630851e8_story.html"

        f1 = Feed.create(
            name="feed1",
            url="https://raw.githubusercontent.com/DocNow/diffengine/master/test-data/feed1.xml",
        )
        f1.get_latest()

        f2 = Feed.create(
            name="feed2",
            url="https://raw.githubusercontent.com/DocNow/diffengine/master/test-data/feed2.xml",
        )
        f2.get_latest()

        assert f1.entries.where(Entry.url == url).count() == 1
        assert f2.entries.where(Entry.url == url).count() == 1

        e = Entry.get(Entry.url == url)
        assert FeedEntry.select().where(FeedEntry.entry == e).count() == 2

    def test_bad_feed_url(self):
        # bad feed url shouldn't cause a fatal exception
        f = Feed.create(name="feed1", url="http://example.org/feedfeed.xml")
        f.get_latest()
        assert True

    def test_whitespace(self):
        e = self.feed.entries[0]
        v1 = e.versions[-1]

        # add some whitespace
        v1.summary = v1.summary + "\n\n    "
        v1.save()

        # whitespace should not count when diffing
        v2 = e.get_latest()
        assert v2 == None


class EnvVarsTest(TestCase):
    def test_config_file_integration(self):
        # test values
        public_value = "public value"
        private_yaml_key = "${PRIVATE_VAR}"
        private_value = "private value"

        # create dot env that that will read
        dotenv_file = open(home_path(".env"), "w+")
        dotenv_file.write("PRIVATE_VAR=%s\n" % private_value)
        dotenv_file.close()

        # create config.yaml that will be read
        test_config = {
            "example": {"private_value": private_yaml_key, "public_value": public_value}
        }
        generate_config(test_home, test_config)

        # test!
        new_config = load_config()
        assert new_config["example"]["public_value"] == public_value
        assert new_config["example"]["private_value"] != private_yaml_key
        assert new_config["example"]["private_value"] == private_value


class WebdriverTest(TestCase):
    def test_geckodriver_when_webdriver_is_not_defined(self):
        # create config.yaml that will be read
        browser = setup_browser()
        assert isinstance(browser, webdriver.Firefox) == True

    def test_raises_when_unknown_webdriver(self):
        with pytest.raises(UnknownWebdriverError):
            # create config.yaml that will be read
            setup_browser("wrong_engine")

    def test_webdriver_is_geckodriver(self):
        # create config.yaml that will be read
        browser = setup_browser("geckodriver")
        assert isinstance(browser, webdriver.Firefox) == True

    def test_webdriver_is_chromedriver(self):
        # create config.yaml that will be read
        browser = setup_browser("chromedriver")
        assert isinstance(browser, webdriver.Chrome) == True


class EntryTest(TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    def test_stale_is_skipped(self):
        # Prepare
        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=False)

        # Test
        result = process_entry(entry, None, None)

        # Assert
        assert result["skipped"] == 1

    def test_raise_if_entry_retrieve_fails(self):
        # Prepare
        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(side_effect=Exception("TEST"))

        # Test
        result = process_entry(entry, None, None)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 0

    def test_get_none_if_no_new_version(self):
        # Prepare
        twitter = MagicMock()
        twitter.tweet_diff = MagicMock()

        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(return_value=None)

        # Test
        result = process_entry(entry, None, twitter)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 0
        twitter.tweet_diff.assert_not_called()

    def test_do_not_tweet_if_entry_has_no_diff(self):
        # Prepare
        twitter = MagicMock()
        twitter.tweet_diff = MagicMock()

        version = MagicMock()
        type(version).diff = PropertyMock(return_value=None)

        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(return_value=version)

        # Test
        result = process_entry(entry, None, twitter)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 1
        twitter.tweet_diff.assert_not_called()

    def test_do_not_tweet_if_feed_has_no_token(self):
        # Prepare
        twitter = MagicMock()
        twitter.tweet_diff = MagicMock()

        version = MagicMock()
        type(version).diff = PropertyMock(return_value=None)

        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(return_value=version)

        # Test
        result = process_entry(entry, None, twitter)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 1
        twitter.tweet_diff.assert_not_called()

    def test_do_tweet_if_entry_has_diff(self):
        # Prepare
        twitter = MagicMock()
        twitter.tweet_diff = MagicMock()

        version = MagicMock()
        type(version).diff = PropertyMock(return_value=MagicMock())

        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(return_value=version)

        # Test
        token = {"access_token": "test", "access_token_secret": "test"}
        result = process_entry(entry, {"twitter": token}, twitter)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 1
        twitter.tweet_diff.assert_called_once()

    def test_do_mail_if_entry_has_diff(self):
        # Prepare
        sendgrid = MagicMock()
        sendgrid.publish_diff = MagicMock()

        version = MagicMock()
        type(version).diff = PropertyMock(return_value=MagicMock())

        entry = MagicMock()
        type(entry).stale = PropertyMock(return_value=True)
        entry.get_latest = MagicMock(return_value=version)

        # Test
        sendgrid_config = {
            "api_token": "12345",
            "sender": "test@test.test",
            "receivers": "test@test.test",
        }
        result = process_entry(entry, {"sendgrid": sendgrid_config}, None, sendgrid)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 1
        sendgrid.publish_diff.assert_called_once()


class TwitterHandlerTest(TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    def test_raises_if_no_config_set(self):
        self.assertRaises(TwitterConfigNotFoundError, TwitterHandler, None, None)
        self.assertRaises(
            TwitterConfigNotFoundError, TwitterHandler, "myConsumerKey", None
        )
        self.assertRaises(
            TwitterConfigNotFoundError, TwitterHandler, None, "myConsumerSecret"
        )

        try:
            TwitterHandler("myConsumerKey", "myConsumerSecret")
        except TwitterConfigNotFoundError:
            self.fail("Twitter.__init__ raised ConfigNotFoundError unexpectedly!")

    def test_raises_if_no_token_provided(self):
        diff = MagicMock()
        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        self.assertRaises(TokenNotFoundError, twitter.tweet_diff, diff, None)

    def test_raises_if_already_tweeted(self):
        diff = MagicMock()
        type(diff).tweeted = PropertyMock(return_value=True)

        token = {
            "access_token": "myAccessToken",
            "access_token_secret": "myAccessTokenSecret",
        }

        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        self.assertRaises(AlreadyTweetedError, twitter.tweet_diff, diff, token)

    def test_raises_if_not_all_archive_urls_are_present(self):
        diff = get_mocked_diff(False)
        token = {
            "access_token": "myAccessToken",
            "access_token_secret": "myAccessTokenSecret",
        }

        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        self.assertRaises(
            TwitterAchiveUrlNotFoundError, twitter.tweet_diff, diff, token
        )

        type(diff.old).archive_url = PropertyMock(return_value="http://test.url/old")
        self.assertRaises(
            TwitterAchiveUrlNotFoundError, twitter.tweet_diff, diff, token
        )

        type(diff.new).archive_url = PropertyMock(return_value="http://test.url/new")
        try:
            twitter.tweet_diff(diff, token)
        except TwitterAchiveUrlNotFoundError:
            self.fail("twitter.tweet_diff raised AchiveUrlNotFoundError unexpectedly!")

    class MockedStatus(MagicMock):
        id_str = PropertyMock(return_value="1234567890")

    @patch("tweepy.OAuthHandler.get_username", return_value="test_user")
    @patch("tweepy.API.update_with_media", return_value=MockedStatus)
    @patch("diffengine.TwitterHandler.create_thread")
    def test_create_thread_if_old_entry_has_no_related_tweet(
        self, mocked_create_thread, mocked_update_with_media, mocked_get_username
    ):

        entry = MagicMock()
        type(entry).tweet_status_id_str = PropertyMock(return_value=None)

        diff = get_mocked_diff()
        type(diff.old).entry = entry

        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        twitter.tweet_diff(
            diff,
            {
                "access_token": "myAccessToken",
                "access_token_secret": "myAccessTokenSecret",
            },
        )

        mocked_create_thread.assert_called_once()
        mocked_update_with_media.assert_called_once()
        mocked_get_username.assert_called()

    @patch("tweepy.OAuthHandler.get_username", return_value="test_user")
    @patch("tweepy.API.update_with_media", return_value=MockedStatus)
    def test_update_thread_if_old_entry_has_related_tweet(
        self, mocked_update_with_media, mocked_get_username
    ):
        entry = MagicMock()
        type(entry).tweet_status_id_str = PropertyMock(return_value="1234567890")

        diff = get_mocked_diff()
        type(diff.old).entry = entry
        type(diff.new).tweet_status_id_str = PropertyMock()
        type(diff.new).save = MagicMock()
        type(diff).tweeted = PropertyMock(return_value=False)
        type(diff).save = MagicMock()

        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        twitter.tweet_diff(
            diff,
            {
                "access_token": "myAccessToken",
                "access_token_secret": "myAccessTokenSecret",
            },
        )

        mocked_update_with_media.assert_called_once()
        mocked_get_username.assert_called_once()
        diff.new.save.assert_called_once()
        diff.save.assert_called_once()

    @patch("tweepy.OAuthHandler.get_username", return_value="test_user")
    @patch("tweepy.API.update_with_media", side_effect=Exception)
    def test_raise_when_thread_tweet_fails(
        self, mocked_update_with_media, mocked_get_username
    ):
        entry = MagicMock()
        type(entry).tweet_status_id_str = PropertyMock(return_value="1234567890")

        diff = get_mocked_diff()
        type(diff.old).entry = entry
        type(diff.new).tweet_status_id_str = PropertyMock()
        type(diff.new).save = MagicMock()
        type(diff).tweeted = PropertyMock(return_value=False)
        type(diff).save = MagicMock()

        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        twitter.tweet_diff(
            diff,
            {
                "access_token": "myAccessToken",
                "access_token_secret": "myAccessTokenSecret",
            },
        )

        mocked_update_with_media.assert_called_once()
        mocked_get_username.assert_not_called()
        diff.new.save.assert_not_called()
        diff.save.assert_not_called()

    @patch("tweepy.API.update_status", side_effect=Exception)
    def test_create_thread_failure(self, mocked_update_status):
        entry = MagicMock()
        version = MagicMock()
        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")
        self.assertRaises(
            UpdateStatusError,
            twitter.create_thread,
            entry,
            version,
            {
                "access_token": "myAccessToken",
                "access_token_secret": "myAccessTokenSecret",
            },
        )
        mocked_update_status.assert_called_once()

    @patch("tweepy.API.update_status", return_value=MockedStatus)
    def test_create_thread_success(self, mocked_update_status):
        entry = MagicMock()
        type(entry).save = MagicMock()
        version = MagicMock()
        type(version).save = MagicMock()
        twitter = TwitterHandler("myConsumerKey", "myConsumerSecret")

        status_id_str = twitter.create_thread(
            entry,
            version,
            {
                "access_token": "myAccessToken",
                "access_token_secret": "myAccessTokenSecret",
            },
        )

        self.assertEqual(status_id_str, mocked_update_status.return_value.id_str)

        mocked_update_status.assert_called_once()
        entry.save.assert_called_once()
        version.save.assert_called_once()


class SendgridHandlerTest(TestCase):
    config = {
        "sendgrid": {
            "api_token": "12345",
            "sender": "test@test.test",
            "receivers": "test@test.test",
        }
    }

    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    def test_raises_if_no_config_set(self):
        diff = MagicMock()
        type(diff).emailed = PropertyMock(return_value=False)
        sendgrid = SendgridHandler({})

        self.assertRaises(SendgridConfigNotFoundError, sendgrid.publish_diff, diff, {})
        try:
            sendgrid.publish_diff(diff, self.config["sendgrid"])
        except SendgridConfigNotFoundError:
            self.fail("sendgrid.publish_diff raised ConfigNotFoundError unexpectedly!")

    def test_raises_if_already_emailed(self):
        diff = MagicMock()
        type(diff).emailed = PropertyMock(return_value=True)

        sendgrid = SendgridHandler(self.config["sendgrid"])
        self.assertRaises(
            AlreadyEmailedError, sendgrid.publish_diff, diff, self.config["sendgrid"]
        )

    def test_raises_if_not_all_archive_urls_are_present(self):
        diff = get_mocked_diff(False)

        sendgrid = SendgridHandler(self.config["sendgrid"])
        self.assertRaises(
            SendgridArchiveUrlNotFoundError,
            sendgrid.publish_diff,
            diff,
            self.config["sendgrid"],
        )

        type(diff.old).archive_url = PropertyMock(return_value="http://test.url/old")
        self.assertRaises(
            SendgridArchiveUrlNotFoundError,
            sendgrid.publish_diff,
            diff,
            self.config["sendgrid"],
        )

        type(diff.new).archive_url = PropertyMock(return_value="http://test.url/new")
        try:
            sendgrid.publish_diff(diff, self.config["sendgrid"])
        except SendgridArchiveUrlNotFoundError:
            self.fail(
                "sendgrid.publish_diff raised AchiveUrlNotFoundError unexpectedly!"
            )


def get_mocked_diff(with_archive_urls=True):
    old = MagicMock()
    type(old).archive_url = None

    new = MagicMock()
    type(new).archive_url = None

    diff = MagicMock()
    type(diff).tweeted = PropertyMock(return_value=False)
    type(diff).emailed = PropertyMock(return_value=False)
    type(diff).old = old
    type(diff).new = new

    if with_archive_urls:
        type(old).archive_url = PropertyMock(return_value="http://test.url/old")
        type(new).archive_url = PropertyMock(return_value="http://test.url/new")

    return diff


class TextBuilderTest(TestCase):
    @patch("logging.warning")
    @patch("diffengine.text_builder.build_with_lang")
    @patch("diffengine.text_builder.build_with_default_content")
    def test_build_with_default_content_when_no_lang_given(
        self, mocked_build_with_default_content, mocked_build_from_lang, mocked_warning
    ):
        diff = get_mocked_diff()
        type(diff.new).title = PropertyMock(return_value="Test")
        type(diff).url = PropertyMock(return_value="https://this.is/a-test")

        build_text(diff)

        mocked_warning.assert_not_called()
        mocked_build_with_default_content.assert_called_once()
        mocked_build_from_lang.assert_not_called()

    @patch("logging.warning")
    @patch("diffengine.text_builder.build_with_lang")
    @patch("diffengine.text_builder.build_with_default_content")
    def test_build_with_default_content_when_lang_is_incomplete(
        self, mocked_build_with_default_content, mocked_build_from_lang, mocked_warning
    ):
        diff = get_mocked_diff()
        type(diff.new).title = PropertyMock(return_value="Test")
        type(diff).url = PropertyMock(return_value="https://this.is/a-test")

        lang = {
            "change_in": "change in",
            "the_url": "the URL",
            "the_title": "the title",
        }
        build_text(diff, lang)

        mocked_warning.assert_called_once()
        mocked_build_with_default_content.assert_called_once()
        mocked_build_from_lang.assert_not_called()

    @patch("logging.warning")
    @patch("diffengine.text_builder.build_with_lang")
    @patch("diffengine.text_builder.build_with_default_content")
    def test_build_with_lang_when_lang_given(
        self, mocked_build_with_default_content, mocked_build_from_lang, mocked_warning
    ):
        diff = get_mocked_diff()
        type(diff.new).title = PropertyMock(return_value="Test")
        type(diff).url = PropertyMock(return_value="https://this.is/a-test")

        lang = {
            "change_in": "change in",
            "the_url": "the URL",
            "the_title": "the title",
            "and": "and",
            "the_summary": "the summary",
        }
        build_text(diff, lang)

        mocked_warning.assert_not_called()
        mocked_build_with_default_content.assert_not_called()
        mocked_build_from_lang.assert_called_once()

    @patch("diffengine.text_builder.build_with_lang")
    def test_default_content_text(self, mocked_build_from_lang):
        diff = get_mocked_diff()
        type(diff.new).title = "Test"
        type(diff).url = "https://this.is/a-test"

        text = build_text(diff)

        mocked_build_from_lang.assert_not_called()
        self.assertEqual(text, "%s %s" % (diff.new.title, diff.url))

        lang = {
            "change_in": "change in",
            "the_url": "the URL",
            "the_title": "the title",
        }
        text = build_text(diff, lang)

        mocked_build_from_lang.assert_not_called()
        self.assertEqual(text, "%s %s" % (diff.new.title, diff.url))

    def test_lang_content_text(self):
        diff = get_mocked_diff()
        lang = {
            "change_in": "change in",
            "the_url": "the URL",
            "the_title": "the title",
            "and": "and",
            "the_summary": "the summary",
        }

        type(diff).url_changed = True
        type(diff).title_changed = False
        type(diff).summary_changed = False
        type(diff).url = "https://this.is/a-test"

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the URL\n%s" % diff.url)

        type(diff).url_changed = False
        type(diff).title_changed = True
        type(diff).summary_changed = False

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the title\n%s" % diff.url)

        type(diff).url_changed = False
        type(diff).title_changed = False
        type(diff).summary_changed = True

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the summary\n%s" % diff.url)

        type(diff).url_changed = True
        type(diff).title_changed = True
        type(diff).summary_changed = False

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the URL and the title\n%s" % diff.url)

        type(diff).url_changed = True
        type(diff).title_changed = False
        type(diff).summary_changed = True

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the URL and the summary\n%s" % diff.url)

        type(diff).url_changed = False
        type(diff).title_changed = True
        type(diff).summary_changed = True

        text = build_text(diff, lang)
        self.assertEqual(text, "change in the title and the summary\n%s" % diff.url)

        type(diff).url_changed = True
        type(diff).title_changed = True
        type(diff).summary_changed = True

        text = build_text(diff, lang)
        self.assertEqual(
            text, "change in the URL, the title and the summary\n%s" % diff.url
        )
