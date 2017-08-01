from typing import Optional, Tuple


def get_paginated_indices(offset: Optional[int], limit: Optional[int], length: int) -> Tuple[int, int]:  # pylint: disable=invalid-sequence-index
    """
    Given an offset and a limit, return the correct starting and ending indices to paginate with that are valid within
    a given length of the item being paginated.
    :param offset: The offset from the starting item for the request
    :param limit: The limit or amount of items for the request
    :param length: The length of the list which we are getting indices to paginate
    """
    # Either both limit and offset are set set or neither are set, so if one or more isn't set
    # then we return the entire list. This usually implies `v1` is being called where we don't paginate at all.
    if offset is None or limit is None:
        return 0, length

    # Remove any negative values.
    offset = max(offset, 0)
    limit = max(limit, 0)

    # If limit is set higher than the number of builds, reduce limit.
    limit = min(length, limit)

    starting_index = offset
    ending_index = min((starting_index + limit), length)

    return starting_index, ending_index
