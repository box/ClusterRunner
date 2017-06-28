import re

class APIVersionHandler(object):
    # List of all versions of the API.
    _versions = [
        1,
        2
    ]

    @classmethod
    def resolve_version(cls, header: str, uri: str):
        """
        Gets the respective version of the API relative to the request header and URI.
        :param header: The value of the header which to search for version type (Content-Type/Accept).
        :type header: str
        :param uri: The URI from the request being checked.
        :type uri: str
        :rtype: int
        """
        matches = re.match(r'.*(?:application/vnd.clusterrunner.v(\d+)\+json).*', header, re.I)
        try:
            matched_version = int(matches.group(1))
            version = cls._get(matched_version, uri)
        except (IndexError, AttributeError, ValueError):
            # No version was found or specified in the request header.
            version = cls._get_default(uri)
        return version

    @classmethod
    def _get(cls, version: int, uri: str):
        """
        Returns the version being requested if it exists, if not it returns the default
        version of the API.
        :rtype int:
        """
        if version in cls._versions:
            return version
        else:
            return cls._get_default(uri)

    @classmethod
    def _get_default(cls, uri: str):
        """
        Get's the default version of the API if none was specified. This takes into account
        the URI of the request.
        :param uri: The URI form the request being checked.
        :type uri: str
        :rtype int:
        """
        if 'v1' in uri.split('/'):
            return cls.get_first()
        else:
            return cls.get_latest()

    @classmethod
    def get_first(cls):
        """
        Returns the first version of the API. This assumes that the first version is the
        version with the lowest value. To ensure we get this value, the list is sorted beforehand.
        :rtype int:
        """
        cls._versions.sort()
        return cls._versions[0]

    @classmethod
    def get_latest(cls):
        """
        Returns the latest version of the API. This assumes that the latest version is the
        version with the highest value. To ensure we get this value, the list is sorted beforehand.
        :rtype int:
        """
        cls._versions.sort()
        return cls._versions[-1]
