import re


class AnyStringMatching(object):
    """
    A helper object that compares equal to any string matching the specified pattern.
    """
    def __init__(self, regex_pattern):
        self._matcher = re.compile(regex_pattern)

    def __eq__(self, other):
        match = self._matcher.search(str(other))
        return isinstance(other, str) and match is not None

    def __repr__(self):
        return '<any string matching "{}">'.format(self._matcher.pattern)


class AnythingOfType(object):
    """
    A helper object that compares equal to any object of the specified type.
    """
    def __init__(self, accepted_type):
        self._type = accepted_type

    def __eq__(self, other):
        return isinstance(other, self._type)

    def __repr__(self):
        return '<any object of type {}>'.format(self._type)
