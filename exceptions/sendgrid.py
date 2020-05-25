class SendgridError(RuntimeError):
    pass


class SendgridConfigNotFoundError(SendgridError):
    """Exception raised if the Sendgrid instance has not the API key"""

    def __init__(self):
        self.message = "Config not set up for feed."


class AlreadyEmailedError(SendgridError):
    def __init__(self, diff_id):
        self.message = "diff %s was already emailed with sendgrid " % diff_id


class SendgridArchiveUrlNotFoundError(SendgridError):
    def __init__(self):
        self.message = "not publishing without archive urls"
