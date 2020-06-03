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
1. `pip3 install diffengine`

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

## Config options

### Database engine

By default the database is configured for Sqlite and the file `./diffengine.db` through the `db` config prop

```yaml
db: sqlite:///diffengine.db
```

This value responds to the [database URL connection string format](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#database-url).

For instance, you can co˚nnect to your postgresql database using something like this.

```yaml
db: postgresql://postgres:my_password@localhost:5432/my_database
```

In case you store your database url connection into an environment var, like in Heroku. You can simply do as follows.

```yaml
db: "${DATABASE_URL}"
```

### Multiple Accounts & Feed Implementation Example

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

```yaml
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

### Skip entry

You can also keep an entry if matches with a regular expression pattern. This is useful for avoid the "subscribe now" pages.
This is configured per feed like so:

```yaml
- name: The Globe and Mail - Report on Business
  skip_pattern: "you have access to only \\d+ articles"
  twitter:
    access_token: ACCESS_TOKEN
    access_token_secret: ACCESS_TOKEN_SECRET
  url: http://www.theglobeandmail.com/report-on-business/?service=rss
```

In this example, if the page says contains the text "you have access to only 10 articles" will skip it. the same if says any number of articles as it's a regular expression.
The `skip_pattern` performs a `re.search` operation and uses the flags for `case insensitive` and `multiline`.

Look for the docs for [more information about Regular Expressions and the search operation.](https://docs.python.org/3/library/re.html#search-vs-match)


### Tweet content

By default, the tweeted diff will include the article's title and the archive diff url, [like this.](https://twitter.com/ld_diff/status/1267989297048817672)

You change this by tweeting what's changed: the url, the title and/or the summary. For doing so, you need to specify **all** the following `lang` keys:

```yaml
lang:
  change_in: "Change in"
  the_url: "the URL"
  the_title: "the title"
  and: "and"
  the_summary: "the summary"
```

Only if all the keys are defined, the tweet will include what's changed on its content, followed by the `diff.url`. Some examples:

- "Change in the title"
- "Change in the summary"
- "Change in the title and the summary"

And so on with all the possible combinations between url, title and summary

### Support for environment vars

The configuration file has support for [environment variables](https://medium.com/chingu/an-introduction-to-environment-variables-and-how-to-use-them-f602f66d15fa). This is useful if you want to keeping your credentials secure when deploying to Heroku, Vercel (former ZEIT Now), AWS, Azure, Google Cloud or any other similar services. The environment variables are defined on the app of the platform you use or directly in a [dotenv file](https://12factor.net/config), which is the usual case when coding locally.

For instance, say you want to keep your Twitter credentials safe. You'd keep a reference to it in the `config.yaml` this way:

```yaml
twitter:
  consumer_key: "${MY_CONSUMER_KEY_ENV_VAR}"
  consumer_secret: "${MY_CONSUMER_SECRET_ENV_VAR}"
```

Then you would define your environment variables `MY_CONSUMER_KEY_ENV_VAR` and `MY_CONSUMER_SECRET_ENV_VAR` in your `.env` file:

```dotenv
MY_CONSUMER_KEY_ENV_VAR="CONSUMER_KEY"
MY_CONSUMER_SECRET_ENV_VAR="CONSUMER_SECRET"
```

Done! You can use diffengine as usual and keep your credentials safe.

### Adding a Twitter account when the configuration file is already created

You can use the following command for adding Twitter accounts to the config file.

```shell
$ diffengine --add

Log in to https://twitter.com as the user you want to tweet as and hit enter.
Visit https://api.twitter.com/oauth/authorize?oauth_token=QKGAqgAAAAABDsonAAABcbfQfFw in your browser and hit enter.
What is your PIN: 1234567

These are your access token and secret.
DO NOT SHARE THEM WITH ANYONE!

ACCESS_TOKEN
xxxxxxxxxxx-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy

ACCESS_TOKEN_SECRET
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
```

Then you would use the `ACCESS_TOKEN` and the `ACCESS_TOKEN_SECRET` inside the config like this

```yaml
feeds:
- name: My new feed
  url: http://www.mynewfeed.com/feed/
  twitter:
    access_token: "${ACCESS_TOKEN}"
    access_token_secret: "${ACCESS_TOKEN_SECRET}"
```

### Avaiable webdriver engines

Diffengine has support for `geckodriver` and `chromedriver`.

You can configure this in the `config.yaml`. The keys are the following ones.
```yaml
webdriver:
  engine:
  executable_path:
  binary_location:
```

#### Configuring geckodriver

The `geckodriver` is properly defined by default. In case you need to configure it, then:

```yaml
webdriver:
  engine: "geckodriver"
  executable_path: null (this config has no use with geckodriver)
  binary_location: null (the same as above with this one)
```

#### Configuring chromedriver

If you want to use `chromedriver` locally, then you should leave the config this way:

```yaml
webdriver:
  engine: "chromedriver"
  executable_path: null ("chromedriver" by default)
  binary_location: null ("" by default)
```

##### Using chromedriver in Heroku

If you use Heroku, then you have to add the [Heroku chromedriver buildpack](https://github.com/heroku/heroku-buildpack-chromedriver).
And then use the environment vars provided automatically by it.

```yaml
webdriver:
  engine: "chromedriver"
  executable_path: "${CHROMEDRIVER_PATH}"
  binary_location: "${GOOGLE_CHROME_BIN}"
```

### Configuring the loggers

By default, the script will log everyhintg to `./diffengine.log`.
Anyway, you can disable the file logger and/or enable the console logger as well.
You can modify the log filename, too.

If no present, the default values will be the following ones.
```yaml
log: diffengine.log
logger:
  file: true
  console : false
```

Logging to the console could be useful to see what's happening if the app lives in services like Heroku.

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

Last, you need to install the pre-commit hooks to be run before any commit

```
pre-commit install
```

This way, [Black](https://black.readthedocs.io/en/stable/) formatter will be executed every time.

We recommend you to [to configure it in your own IDE here.](https://black.readthedocs.io/en/stable/editor_integration.html)


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
