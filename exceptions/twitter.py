class TwitterError(RuntimeError):
    pass


class ConfigNotFoundError(TwitterError):
    """Exception raised if the Twitter instance has not the required key and secret"""

    def __init__(self):
        self.message = "consumer key/secret not set up for feed."


class TokenNotFoundError(TwitterError):
    """Exception raised if no token is preset"""

    def __init__(self):
        self.message = "access token/secret not set up for feed"


class AlreadyTweetedError(TwitterError):
    def __init__(self, diff_id):
        self.message = "diff %s has already been tweeted" % diff_id


class AchiveUrlNotFoundError(TwitterError):
    def __init__(self):
        self.message = "not tweeting without archive urls"


class UpdateStatusError(TwitterError):
    def __init__(self, entry):
        self.message = "could not create thread on entry id %s, url %s" % (
            entry.id,
            entry.url,
        )
