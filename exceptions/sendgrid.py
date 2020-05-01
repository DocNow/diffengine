class SendgridError(RuntimeError):
    pass


class ConfigNotFoundError(SendgridError):
    """Exception raised if the Sendgrid instance has not the API key"""

    def __init__(self):
        self.message = "API key not set up for feed."


class AlreadyEmailedError(SendgridError):
    def __init__(self, diff_id):
        self.message = "diff %s was already emailed with sendgrid " % diff_id


class AchiveUrlNotFoundError(SendgridError):
    def __init__(self):
        self.message = "not publishing without archive urls"
