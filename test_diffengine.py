import os
import re
import setup
import pytest
import shutil

from diffengine import *

if os.path.isdir("test"):
    shutil.rmtree("test")

# set things up but disable prompting for initial feed
test_home = "test"
init(test_home, prompt=False)

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


@pytest.mark.skipif(
    os.environ.get("TRAVIS") is not None, reason="this .env test fails on Travis"
)
def test_environment_vars_in_config_file():

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
