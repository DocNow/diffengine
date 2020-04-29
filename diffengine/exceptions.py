class UnknownWebdriverError(RuntimeError):
    """Exception raised if the indicated webdriver is unknown

    Attributes:
        driver -- the indicated webdriver in the configuratoin file
    """

    def __init__(self, driver):
        self.message = (
            'webdriver "%s" is not a valid engine. Please indicate one of "chromedriver" or "geckodriver" and restart the process.'
            % driver
        )


class TwitterConfigError(RuntimeError):
    """Exception raised if the Twitter instance has not the required key and secret"""

    def __init__(self):
        self.message = "consumer key/secret not set up for feed."
