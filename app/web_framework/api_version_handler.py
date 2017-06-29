import re


class APIVersionHandler():
    OLD_VERSIONED_URI_COMPONENT = 'v1'
    API_VERSION_HEADER_KEY = 'Api-Version'

    _versions = [
        1,
        2
    ]

    @classmethod
    def resolve_version(cls, accept_header_value: str, uri: str) -> int:
        """
        Get the respective version of the API relative to the request header and URI.
        :param accept_header_value: The value of the header which to search for version type (Content-Type/Accept).
        :param uri: The URI from the request being checked.
        """
        version = cls._get_default(uri)
        try:
            matches = re.match(r'.*(?:application/vnd.clusterrunner.v(\d+)\+json).*',
                               accept_header_value, re.I)
            matched_version = int(matches.group(1))
            version = matched_version if matched_version in cls._versions else cls._get_default(uri)
        except (IndexError, AttributeError, ValueError):
            # No version was found or specified in the request header.
            pass

        return version

    @classmethod
    def get_first(cls) -> int:
        """
        Return the first version of the API. This assumes that the first version is the
        version with the lowest value.
        """
        return min(cls._versions)

    @classmethod
    def get_latest(cls) -> int:
        """
        Return the latest version of the API. This assumes that the latest version is the
        version with the highest value.
        """
        return max(cls._versions)

    @classmethod
    def _get_default(cls, uri: str) -> int:
        """
        Get the default version of the API if none was specified. This takes into account
        the URI of the request.
        :param uri: The URI from the request being checked.
        """
        first_uri_component = next((part for part in uri.split('/') if part != ''), None)
        if first_uri_component == cls.OLD_VERSIONED_URI_COMPONENT:
            return cls.get_first()
        else:
            return cls.get_latest()
