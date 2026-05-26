class GorzdravError(Exception):
    def __init__(self, message: str, error_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class GorzdravTransientError(GorzdravError):
    pass


class GorzdravPermanentError(GorzdravError):
    pass


class GorzdravConflictError(GorzdravPermanentError):
    pass
