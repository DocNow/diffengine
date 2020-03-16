<div style="text: center;">
<img height="100" src="https://github.com/DocNow/diffengine/blob/master/diffengine.png?raw=true">
</div>

diffengine is a utility for watching RSS feeds to see when story content
changes. When new content is found a snapshot is saved at the Internet Archive,
and a diff is generated for sending to social media. The hope is that it can
help draw attention to the way news is being shaped on the web. It also creates
a database of changes over time that can be useful for research purposes.

diffengine draws heavily on the inspiration of [NYTDiff] and [NewsDiffs] which
*almost* did what we wanted. [NYTdiff] is able to create presentable diff images
and tweet them, but was designed to work specifically with the NYTimes API.
NewsDiffs provides a comprehensive framework for watching changes on multiple
sites (Washington Post, New York Times, CNN, BBC, etc) but you need to be a
programmer to add a [parser
module](https://github.com/ecprice/newsdiffs/tree/master/parsers) for a website
that you want to monitor. It is also a full-on website which involves some
commitment to install and run.

With the help of [feedparser], diffengine takes a different approach by working
with any site that publishes an RSS feed of changes. This covers many news
organizations, but also personal blogs and organizational websites that put out
regular updates. And with the [readability] module, diffengine is able to
automatically extract the primary content of pages, without requiring special
parsing to remove boilerplate material. And like NYTDiff, instead of creating
another website for people to watch, diffengine pushes updates out to social
media where people are already, while also building a local database of diffs
that can be used for research purposes.

## Install 

1. install [GeckoDriver]
1. install [Python 3]
1. `pip3 install --process-dependency-links diffengine`

## Run

In order to run diffengine you need to pick a directory location where you can
store the diffengine configuration, database and diffs. For example I have a
directory in my home directory, but you can use whatever location you want, you
just need to be able to write to it.

The first time you run diffengine it will prompt you to enter an RSS or Atom
feed URL to monitor and will authenticate with Twitter. 

```console
% diffengine /home/ed/.diffengine 

What RSS/Atom feed would you like to monitor? https://inkdroid.org/feed.xml

Would you like to set up tweeting edits? [Y/n] Y

Go to https://apps.twitter.com and create an application.

What is the consumer key? <TWITTER_APP_KEY>

What is the consumer secret? <TWITTER_APP_SECRET>

Log in to https://twitter.com as the user you want to tweet as and hit enter.

Visit https://api.twitter.com/oauth/authorize?oauth_token=NRW9BQAAAAAAyqBnAAXXYYlCL8g

What is your PIN: 8675309

Saved your configuration in /home/ed/.diffengine/config.yaml

Fetching initial set of entries.

Done!
```

After that you just need to put diffengine in your crontab to have it run
regularly, or you can run it manually at your own intervals if you want. Here's
my crontab to run every 30 minutes to look for new content.

    0,30 * * * * /usr/local/bin/diffengine /home/ed/.diffengine

You can examine your config file at any time and add/remove feeds as needed. It
is the `config.yaml` file that is stored relative to the storage directory you
chose, so in my case `/home/ed/.diffengine/config.yaml`.

Logs can be found in `diffengine.log` in the storage directory, for example
`/home/ed/.diffengine/diffengine.log`.

## Examples

Checkout [Ryan Baumann's "diffengine" Twitter list] for a list of known
diffengine Twitter accounts that are out there.

## Multiple Accounts & Feed Implementation Example

If you are setting multiple accounts, and multiple feeds if may be helpful to setup a 
directory for each account. For example:

- Toronto Sun `/home/nruest/.torontosun`
- Toronto Star  `/home/nruest/.torontostar`
- Globe & Mail `/home/nruest/.globemail`
- Canadaland `/home/nruest/.canadaland`
- CBC `/home/nruest/.cbc`

Then you will configure a cron entry for each account:

```
0,15,30,45 * * * * /usr/bin/flock -xn /tmp/globemail.lock -c "/usr/local/bin/diffengine /home/nruest/.globemail"
0,15,30,45 * * * * /usr/bin/flock -xn /tmp/torontosun.lock -c "/usr/local/bin/diffengine /home/nruest/.torontosun"
0,15,30,45 * * * * /usr/bin/flock -xn /tmp/cbc.lock -c "/usr/local/bin/diffengine /home/nruest/.cbc"
0,15,30,45 * * * * /usr/bin/flock -xn /tmp/lapresse.lock -c "/usr/local/bin/diffengine /home/nruest/.lapresse"
0,15,30,45 * * * * /usr/bin/flock -xn /tmp/calgaryherald.lock -c "/usr/local/bin/diffengine /home/nruest/.calgaryherald"
```

If there are multiple feeds for an account, you can setup the `config.yml` like so:

```yml
- name: The Globe and Mail - Report on Business
  twitter:
    access_token: ACCESS_TOKEN
    access_token_secret: ACCESS_TOKEN_SECRET
  url: http://www.theglobeandmail.com/report-on-business/?service=rss
- name: The Globe and Mail - Opinion
  twitter:
    access_token: ACCESS_TOKEN
    access_token_secret: ACCESS_TOKEN_SECRET
  url: http://www.theglobeandmail.com/opinion/?service=rss
- name: The Globe and Mail - News
  twitter:
    access_token: ACCESS_TOKEN
    access_token_secret: ACCESS_TOKEN_SECRET
  url: http://www.theglobeandmail.com/news/?service=rss
twitter:
  consumer_key: CONSUMER_KEY
  consumer_secret: CONSUMER_SECRET
```

## Develop

[![Build Status](https://travis-ci.org/DocNow/diffengine.svg)](http://travis-ci.org/DocNow/diffengine)

Here's how to get started hacking on diffengine with [pipenv]:

```console
% git clone https://github.com/docnow/diffengine 
% cd diffengine
% pipenv install
% pytest
============================= test session starts ==============================
platform linux -- Python 3.5.2, pytest-3.0.5, py-1.4.32, pluggy-0.4.0
rootdir: /home/ed/Projects/diffengine, inifile:
collected 5 items

test_diffengine.py .....

=========================== 5 passed in 8.09 seconds ===========================
```

[nyt_diff]: https://twitter.com/nyt_diff
[NYTDiff]: https://github.com/j-e-d/NYTdiff
[NewsDiffs]: http://newsdiffs.org/
[feedparser]: https://pythonhosted.org/feedparser/
[readability]: https://github.com/buriy/python-readability
[GeckoDriver]: https://github.com/mozilla/geckodriver
[Python 3]: https://python.org
[create an issue]: https://github.com/DocNow/diffengine/issues
[pipenv]: https://pipenv.readthedocs.io/en/latest/
[Ryan Baumann's "diffengine" Twitter list]: https://twitter.com/ryanfb/lists/diffengine
