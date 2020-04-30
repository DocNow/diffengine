import os
import re

import yaml
from selenium import webdriver

import setup
import pytest
import shutil

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
)
from exceptions.twitter import (
    ConfigNotFoundError,
    TokenNotFoundError,
    AlreadyTweetedError,
    AchiveUrlNotFoundError,
    UpdateStatusError,
)

if os.path.isdir("test"):
    shutil.rmtree("test")

# set things up but disable prompting for initial feed
init("test", prompt=False)

# the sequence of these tests is significant


def test_version():
    assert setup.version in UA


def test_feed():
    f = Feed.create(name="Test", url="https://inkdroid.org/feed.xml")
    f.get_latest()
    assert f.created
    assert len(f.entries) == 10


def test_entry():
    f = Feed.get(Feed.url == "https://inkdroid.org/feed.xml")
    e = f.entries[0]
    v = e.get_latest()
    assert type(v) == EntryVersion
    assert len(e.versions) == 1


def test_diff():
    f = Feed.get(Feed.url == "https://inkdroid.org/feed.xml")
    e = f.entries[0]
    v1 = e.versions[0]

    # remove some characters from the version
    v1.summary = v1.summary[0:-20]
    v1.save()

    v2 = e.get_latest()
    assert type(v2) == EntryVersion
    assert v2.diff
    assert v2.archive_url is not None
    assert (
        re.match("^https://web.archive.org/web/[0-9]+/.+$", v2.archive_url) is not None
    )

    diff = v2.diff
    assert diff.old == v1
    assert diff.new == v2
    assert os.path.isfile(diff.html_path)
    assert os.path.isfile(diff.screenshot_path)
    assert os.path.isfile(diff.thumbnail_path)

    # check that the url for the internet archive diff is working
    assert re.match("^https://web.archive.org/web/diff/\d+/\d+/https.+$", diff.url)


def test_html_diff():
    f = Feed.get(Feed.url == "https://inkdroid.org/feed.xml")
    e = f.entries[0]

    # add a change to the summary that htmldiff ignores
    v1 = e.versions[-1]
    parts = v1.summary.split()
    parts.insert(2, "<br>   \n")
    v1.summary = " ".join(parts)
    v1.save()

    v2 = e.get_latest()
    assert v2 is None


def test_many_to_many():

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


def test_bad_feed_url():
    # bad feed url shouldn't cause a fatal exception
    f = Feed.create(name="feed1", url="http://example.org/feedfeed.xml")
    f.get_latest()
    assert True


def test_whitespace():
    f = Feed.get(url="https://inkdroid.org/feed.xml")
    e = f.entries[0]
    v1 = e.versions[-1]

    # add some whitespace
    v1.summary = v1.summary + "\n\n    "
    v1.save()

    # whitespace should not count when diffing
    v2 = e.get_latest()
    assert v2 == None


def test_fingerprint():
    from diffengine import _fingerprint

    assert _fingerprint("foo bar") == "foobar"
    assert _fingerprint("foo bar\nbaz") == "foobarbaz"
    assert _fingerprint("foo<br>bar") == "foobar"
    assert _fingerprint("foo'bar") == "foobar"
    assert _fingerprint("foo’bar") == "foobar"


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
        config_file = home_path("config.yaml")
        yaml.dump(test_config, open(config_file, "w"), default_flow_style=False)

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
        entry.get_latest = MagicMock(side_effect=Exception)

        # Test
        result = process_entry(entry, None, None)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 0

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
        result = process_entry(entry, token, twitter)

        # Assert
        entry.get_latest.assert_called_once()
        assert result["checked"] == 1
        assert result["new"] == 1
        twitter.tweet_diff.assert_called_once()


class TwitterHandlerTest(TestCase):
    def test_raises_if_no_config_set(self):
        self.assertRaises(ConfigNotFoundError, TwitterHandler, None, None)
        self.assertRaises(ConfigNotFoundError, TwitterHandler, "myConsumerKey", None)
        self.assertRaises(ConfigNotFoundError, TwitterHandler, None, "myConsumerSecret")

        try:
            TwitterHandler("myConsumerKey", "myConsumerSecret")
        except ConfigNotFoundError:
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
        self.assertRaises(AchiveUrlNotFoundError, twitter.tweet_diff, diff, token)

        type(diff.old).archive_url = PropertyMock(return_value="http://test.url/old")
        self.assertRaises(AchiveUrlNotFoundError, twitter.tweet_diff, diff, token)

        type(diff.new).archive_url = PropertyMock(return_value="http://test.url/new")
        try:
            twitter.tweet_diff(diff, token)
        except AchiveUrlNotFoundError:
            self.fail("twitter.tweet_diff raised AchiveUrlNotFoundError unexpectedly!")

    @patch("tweepy.OAuthHandler.get_username", return_value="test_user")
    @patch("diffengine.TwitterHandler.create_thread")
    def test_create_thread_if_old_entry_has_no_related_tweet(
        self, mocked_create_thread, mocked_get_username
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
        mocked_get_username.assert_called_once()

    @patch("tweepy.OAuthHandler.get_username", return_value="test_user")
    @patch("diffengine.TwitterHandler.create_thread")
    def test_update_thread_if_old_entry_has_related_tweet(
        self, mocked_create_thread, mocked_get_username
    ):

        entry = MagicMock()
        type(entry).tweet_status_id_str = PropertyMock(return_value="1234567890")

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

        mocked_create_thread.assert_not_called()
        mocked_get_username.assert_called_once()

    class MockedStatus(MagicMock):
        id_str = PropertyMock(return_value="1234567890")

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


def get_mocked_diff(with_archive_urls=True):
    old = MagicMock()
    type(old).archive_url = None

    new = MagicMock()
    type(new).archive_url = None

    diff = MagicMock()
    type(diff).tweeted = PropertyMock(return_value=False)
    type(diff).old = old
    type(diff).new = new

    if with_archive_urls:
        type(old).archive_url = PropertyMock(return_value="http://test.url/old")
        type(new).archive_url = PropertyMock(return_value="http://test.url/new")

    return diff
