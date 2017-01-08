import os
import PIL
import pytest
import shutil

from diffengine import *

if os.path.isdir("test"):
    shutil.rmtree("test")

init("test")

# the sequence of these tests is significant

def test_feed():
    f = Feed.create(name="Test", url="https://inkdroid.org/feed.xml")
    f.get_latest()
    assert f.created
    assert len(f.entries) == 10

def test_entry():
    f = Feed.get(Feed.url=="https://inkdroid.org/feed.xml")
    e = f.entries[0]
    v = e.get_latest()
    assert type(v) == EntryVersion
    assert len(e.versions) == 1

def test_diff():
    f = Feed.get(Feed.url=="https://inkdroid.org/feed.xml")
    e = f.entries[0]
    v1 = e.versions[0]

    # remove some characters from the version
    v1.summary = v1.summary[0:-20]
    v1.save()

    v2 = e.get_latest(force=True)
    assert type(v2) == EntryVersion
    assert v2.next_diff

    diff = v2.next_diff
    assert diff.old == v1
    assert diff.new == v2
    assert os.path.isfile(diff.html_path)
    assert os.path.isfile(diff.screenshot_path)
    assert os.path.isfile(diff.thumbnail_path)

def test_many_to_many():

    # these two feeds share this entry, we want diffengine to support
    # multiple feeds for the same content, which is fairly common at 
    # large media organizations with multiple topical feeds
    url="https://www.washingtonpost.com/classic-apps/how-a-week-of-tweets-by-trump-stoked-anxiety-moved-markets-and-altered-plans/2017/01/07/38be8e64-d436-11e6-9cb0-54ab630851e8_story.html"

    f1 = Feed.create(name="feed1", url="file:test-data/feed1.xml")
    f1.get_latest()

    f2 = Feed.create(name="feed2", url="file:test-data/feed2.xml")
    f2.get_latest()

    assert f1.entries.where(Entry.url==url).count() == 1
    assert f2.entries.where(Entry.url==url).count() == 1

    e = Entry.get(Entry.url==url)
    assert FeedEntry.select().where(FeedEntry.entry==e).count() == 2
