class AtomGrouper(object):
    def __init__(self, atoms, max_processes):
        """
        :param atoms: the list of atoms
        :type atoms: list[app.master.atom.Atom]
        :param max_processes: the maximum number of processes requested for this job
        :type max_processes: int
        """
        self._atoms = atoms
        self._max_processes = max_processes

    def groupings(self):
        """
        Groups together atoms based on whatever strategy we choose.

        For now we are going with the default implementation, which is one atom per grouping.

        :return: a list of lists of atoms
        :rtype: list[list[app.master.atom.Atom]]
        """
        return [[atom] for atom in self._atoms]
