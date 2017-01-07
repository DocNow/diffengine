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
