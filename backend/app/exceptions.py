class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


class ConflictError(Exception):
    pass


class UnverifiedEmailError(Exception):
    pass


class InvalidTokenError(Exception):
    pass
