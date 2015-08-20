from collections import OrderedDict

from app.master.atom_grouper import AtomGrouper


class TimeBasedAtomGrouper(object):
    """
    This class implements the algorithm to best split & group atoms based on historic time values. This algorithm is
    somewhat complicated, so I'm going to give a summary here.
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Let N be the number of concurrent executors allocated for this job.
    Let T be the aggregate serial time to execute all atoms on a single executor.
    Both N and T are known values at the beginning of this algorithm.

    In the ideal subjob atom-grouping, we would have exactly N subjobs, each allocated with T/N amount of work that
    would all end at the same time. However, in reality, there are a few factors that makes this solution unfeasible:

    - There is a significant amount of variability in the times of running these atoms, so numbers are never exact.
    - Certain builds will introduce new tests (for which we don't have historical time data for).
    - Not all of the machines are exactly the same, so we can't expect identical performance.

    We have two aims for this algorithm:

    - Minimize the amount of framework overhead (time spent sending and retrieving subjobs) and maximize the amount of
      time the slaves actually spend running the build.
    - Don't overload any single executor with too much work--this will cause the whole build to wait on a single
      executor. We want to try to get all of the executors to end as close to the same time as possible in order to
      get rid of any inefficient use of slave machines.

    In order to accomplish this, the algorithm implemented by this class tries to split up the majority of the atoms
    into N buckets, and splits up the rest of the atoms into smaller buckets. Hopefully, the timeline graph of
    executed subjobs for each of the executors would end up looking like this:

    [========================================================================][===][==][==]
    [===============================================================================][==]
    [====================================================================][====][===][==][=]
    [========================================================================][===][==][=]
    [=====================================================================][====][==][==]
    [==================================================================================][=]
    [===================================================================][======][==][==]

    The algorithm has two stages of subjob creation: the 'big chunk' stage and the 'small chunk' stage. The 'big chunk'
    stage creates exactly N large subjob groupings that will consist of the majority of atoms (in terms of runtime).
    The 'small chunk' stage creates ~2N short subjob groupings that will be used to fill in the gaps in order to aim for
    having all of the executors end at similar times.

    Notes:
    - For new atoms that we don't have historic times for, we will assign it the highest atom time value in order to
      avoid underestimating the length of unknown atoms.
    - We will have to try tweaking the percentage of T that we want to be allocated for the initial large batch of
      big subjobs. Same goes for the number and size of the smaller buckets.
    """
    BIG_CHUNK_FRACTION = 0.8

    def __init__(self, atoms, max_executors, atom_time_map, project_directory):
        """
        :param atoms: the list of atoms for this build
        :type atoms: list[app.master.atom.Atom]
        :param max_executors: the maximum number of executors for this build
        :type max_executors: int
        :param atom_time_map: a dictionary containing the historic times for atoms for this particular job
        :type atom_time_map: dict[str, float]
        :type project_directory: str
        """
        self._atoms = atoms
        self._max_executors = max_executors
        self._atom_time_map = atom_time_map
        self._project_directory = project_directory

    def groupings(self):
        """
        Group the atoms into subjobs using historic timing data.

        :return: a list of lists of atoms
        :rtype: list[list[app.master.atom.Atom]]
        """
        # 1). Coalesce the atoms with historic atom times, and also get total estimated runtime
        try:
            total_estimated_runtime = self._set_expected_atom_times(
                self._atoms, self._atom_time_map, self._project_directory)
        except _AtomTimingDataError:
            grouper = AtomGrouper(self._atoms, self._max_executors)
            return grouper.groupings()

        # 2). Sort them by decreasing time, and add them to an OrderedDict
        atoms_by_decreasing_time = sorted(self._atoms, key=lambda atom: atom.expected_time, reverse=True)
        sorted_atom_times_left = OrderedDict([(atom, atom.expected_time) for atom in atoms_by_decreasing_time])

        # 3). Group them!

        # Calculate what the target 'big subjob' time is going to be for each executor's initial subjob
        big_subjob_time = (total_estimated_runtime * self.BIG_CHUNK_FRACTION) / self._max_executors
        # Calculate what the target 'small subjob' time is going to be
        small_subjob_time = (total_estimated_runtime * (1.0 - self.BIG_CHUNK_FRACTION)) / (2 * self._max_executors)
        # _group_atoms_into_sized_buckets() will remove elements from sorted_atom_times_left.
        subjobs = self._group_atoms_into_sized_buckets(sorted_atom_times_left, big_subjob_time, self._max_executors)
        small_subjobs = self._group_atoms_into_sized_buckets(sorted_atom_times_left, small_subjob_time, None)

        subjobs.extend(small_subjobs)
        return subjobs

    def _set_expected_atom_times(self, new_atoms, old_atoms_with_times, project_directory):
        """
        Set the expected runtime (new_atom.expected_time) of each atom in new_atoms using historic timing data.

        Additionally, return the total estimated serial-runtime for this build. Although this seems like an odd thing
        for this method to return, it is done here for efficiency. There can be thousands of atoms, and iterating
        through them multiple times seems inefficient.

        :param new_atoms: the list of atoms that will be run in this build
        :type new_atoms: list[app.master.atom.Atom]
        :param old_atoms_with_times: a dictionary containing the historic times for atoms for this particular job
        :type old_atoms_with_times: dict[str, float]
        :type project_directory: str
        :return: the total estimated runtime in seconds
        :rtype: float
        """
        atoms_without_timing_data = []
        total_time = 0
        max_atom_time = 0

        # Generate list for atoms that have timing data
        for new_atom in new_atoms:
            if new_atom.command_string not in old_atoms_with_times:
                atoms_without_timing_data.append(new_atom)
                continue

            new_atom.expected_time = old_atoms_with_times[new_atom.command_string]

            # Discover largest single atom time to use as conservative estimates for atoms with unknown times
            if max_atom_time < new_atom.expected_time:
                max_atom_time = new_atom.expected_time

            # We want to return the atom with the project directory still in it, as this data will directly be
            # sent to the slave to be run.
            total_time += new_atom.expected_time

        # For the atoms without historic timing data, assign them the largest atom time we have
        for new_atom in atoms_without_timing_data:
            new_atom.expected_time = max_atom_time

        if len(new_atoms) == len(atoms_without_timing_data):
            raise _AtomTimingDataError

        total_time += (max_atom_time * len(atoms_without_timing_data))
        return total_time

    def _group_atoms_into_sized_buckets(self, sorted_atom_time_dict, target_group_time, max_groups_to_create):
        """
        Given a sorted dictionary (Python FTW) of [atom, time] pairs in variable sorted_atom_time_dict, return a list
        of lists of atoms that each are estimated to take target_group_time seconds. This method will generate at most
        max_groups_to_create groupings, and will return once this limit is reached or when sorted_atom_time_dict is
        empty.

        Note, this method will modify sorted_atom_time_dict's state by removing elements as needed (often from the
        middle of the collection).

        :param sorted_atom_time_dict: the sorted (longest first), double-ended queue containing [atom, time] pairs.
            This OrderedDict will have elements removed from this method.
        :type sorted_atom_time_dict: OrderedDict[app.master.atom.Atom, float]
        :param target_group_time: how long each subjob should approximately take
        :type target_group_time: float
        :param max_groups_to_create: the maximum number of subjobs to create. Once max_groups_to_create limit is
            reached, this method will return the subjobs that have already been grouped. If set to None, then there
            is no limit.
        :type max_groups_to_create: int|None
        :return: the groups of grouped atoms, with each group taking an estimated target_group_time
        :rtype: list[list[app.master.atom.Atom]]
        """
        subjobs = []
        subjob_time_so_far = 0
        subjob_atoms = []

        while (max_groups_to_create is None or len(subjobs) < max_groups_to_create) and len(sorted_atom_time_dict) > 0:
            for atom, time in sorted_atom_time_dict.items():
                if len(subjob_atoms) == 0 or (time + subjob_time_so_far) <= target_group_time:
                    subjob_time_so_far += time
                    subjob_atoms.append(atom)
                    sorted_atom_time_dict.pop(atom)

                    # If (number of subjobs created so far + atoms left) is less than or equal to the total number of
                    # subjobs we need to create, then have each remaining atom be a subjob and return.
                    # The "+ 1" is here to account for the current subjob being generated, but that hasn't been
                    # appended to subjobs yet.
                    if max_groups_to_create is not None and (len(subjobs) + len(sorted_atom_time_dict) + 1) <= max_groups_to_create:
                        subjobs.append(subjob_atoms)

                        for atom, _ in sorted_atom_time_dict.items():
                            sorted_atom_time_dict.pop(atom)
                            subjobs.append([atom])

                        return subjobs

            subjobs.append(subjob_atoms)
            subjob_atoms = []
            subjob_time_so_far = 0

        return subjobs


class _AtomTimingDataError(Exception):
    """
    An exception to represent the case where the atom timing data is either not present or incorrect.
    """
