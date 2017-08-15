from collections import OrderedDict
from itertools import islice
from typing import List

from app.master.build import Build
from app.util.exceptions import ItemNotFoundError


class BuildStore:
    """
    Build storage service that stores and handles all builds.
    """
    _all_builds_by_id = OrderedDict()

    @classmethod
    def get(cls, build_id: int) -> Build:
        """
        Returns a build by id
        :param build_id: The id for the build whose status we are getting
        """
        build = cls._all_builds_by_id.get(build_id)
        if build is None:
            raise ItemNotFoundError('Invalid build id: {}.'.format(build_id))

        return build

    @classmethod
    def get_range(cls, start: int, end: int) -> List[Build]:
        """
        Returns a list of all builds.
        :param start: The starting index of the requested build
        :param end: 1 + the index of the last requested element, although if this is greater than the total number
                    of builds available the length of the returned list may be smaller than (end - start)
        """
        requested_builds = islice(cls._all_builds_by_id, start, end)
        return [cls._all_builds_by_id[key] for key in requested_builds]

    @classmethod
    def add(cls, build: Build):
        """
        Add new build to collection
        :param build: The build to add to the store
        """
        cls._all_builds_by_id[build.build_id()] = build

    @classmethod
    def size(cls) -> int:
        """
        Return the amount of builds within the store
        """
        return len(cls._all_builds_by_id)
