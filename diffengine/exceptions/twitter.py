class TwitterError(RuntimeError):
    pass


class TwitterConfigNotFoundError(TwitterError):
    """Exception raised if the Twitter instance has not the required key and secret"""

    def __init__(self):
        self.message = "consumer key/secret not set up for feed."


class TokenNotFoundError(TwitterError):
    """Exception raised if no token is preset"""

    def __init__(self):
        self.message = "access token/secret not set up for feed"


class AlreadyTweetedError(TwitterError):
    def __init__(self, diff):
        self.message = "diff %s has already been tweeted" % diff.id


class TwitterAchiveUrlNotFoundError(TwitterError):
    def __init__(self, diff):
        self.message = "not tweeting without archive urls for diff %s" % diff.id


class UpdateStatusError(TwitterError):
    def __init__(self, entry):
        self.message = "could not create thread on entry id %s, url %s" % (
            entry.id,
            entry.url,
        )
