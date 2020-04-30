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
