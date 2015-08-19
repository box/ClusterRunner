

class ItemNotReadyError(Exception):
    """
    An exception to represent the case where something was not yet ready or does not yet exist, but will definitely
    exist at a future point. Example: trying to download the results for a build that has not finished. The web
    framework should translate this exception to a 202 response.
    """


class BadRequestError(Exception):
    """
    An exception to represent the case where something in the request was bad or malformed. Example: bad JSON data in
    request body. The web framework should translate this exception to a 400 response.
    """


class AuthenticationError(Exception):
    """
    An exception to represent the case where authentication credentials were either not present or incorrect. The web
    framework should translate this exception to a 401 response.
    """


class ItemNotFoundError(Exception):
    """
    An exception to represent the case where something was not found. Example: trying to get the status for a
    non-existent build. The web framework should translate this exception to a 404 response.
    """


class PreconditionFailedError(Exception):
    """
    An exception to represent the case when a non-authentication-related precondition for accessing the resource
    was not met. For example, the session id token has expired. The web framework should translate this exception
    to a 412 response.
    """
