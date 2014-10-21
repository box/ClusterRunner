import re


class AnyStringMatching(object):
    """
    A helper object that compares equal to any string matching the specified pattern."
    """
    def __init__(self, pattern):
        self._pattern = pattern

    def __eq__(self, other):
        match = re.search(self._pattern, str(other))
        return isinstance(other, str) and match is not None

    def __repr__(self):
        return '<any string matching "{}">'.format(self._pattern)
