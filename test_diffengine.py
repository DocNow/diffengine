import os
import re

import yaml
from selenium import webdriver

import setup
import pytest
import shutil

from unittest import TestCase
from unittest.mock import MagicMock
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
from diffengine.exceptions import TwitterConfigError

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


class TweetTest(TestCase):
    def test_raises_if_no_config_set(self):
        self.assertRaises(TwitterConfigError, TwitterHandler, None, None)
        self.assertRaises(TwitterConfigError, TwitterHandler, "myConsumerKey", None)
        self.assertRaises(TwitterConfigError, TwitterHandler, None, "myConsumerSecret")

        try:
            TwitterHandler("myConsumerKey", "myConsumerSecret")
        except TwitterConfigError:
            self.fail("Twitter.__init__ raised TwitterConfigError unexpectedly!")

    def test_do_nothing_if(self):
        config = {"twitter": {"consumer_key": "test", "consumer_secret": "test"}}
        twitter = TwitterHandler(config)
