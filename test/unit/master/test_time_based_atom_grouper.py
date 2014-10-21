from app.master.time_based_atom_grouper import TimeBasedAtomGrouper, _AtomTimingDataError
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestTimeBasedAtomGrouper(BaseUnitTestCase):
    def test_coalesce_new_atoms_with_no_atom_times(self):
        new_atoms = ['atom_1', 'atom_2', 'atom_3']
        old_atoms_with_times = dict()
        project_directory = 'some_project_directory'

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, project_directory)

        with self.assertRaises(_AtomTimingDataError):
            atom_grouper._coalesce_new_atoms_with_historic_times(new_atoms, old_atoms_with_times, project_directory)

    def test_coalesce_new_atoms_with_all_atom_times(self):
        new_atoms = ['atom_1', 'atom_2', 'atom_3']
        old_atoms_with_times = dict({'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0})
        expected_contents = {'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        groups, total_time = atom_grouper._coalesce_new_atoms_with_historic_times(new_atoms, old_atoms_with_times, 'some_project_directory')

        self.assertEquals(total_time, 6.0)
        self._assert_coalesced_contents(groups, expected_contents)

    def test_coalesce_new_atoms_with_some_atom_times(self):
        new_atoms = ['atom_2', 'atom_3', 'atom_4', 'atom_5']
        old_atoms_with_times = dict({'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0})
        expected_contents = {'atom_2': 2.0, 'atom_3': 3.0, 'atom_4': 3.0, 'atom_5': 3.0}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        groups, total_time = atom_grouper._coalesce_new_atoms_with_historic_times(new_atoms, old_atoms_with_times, 'some_project_directory')

        self.assertEquals(total_time, 11.0)
        self._assert_coalesced_contents(groups, expected_contents)

    def test_groupings_data_set_1(self):
        new_atoms = [
            'atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5', 'atom_6', 'atom_7', 'atom_8', 'atom_9', 'atom_10']
        old_atoms_with_times = dict({
            'atom_1': 1.0, 'atom_2': 10.0, 'atom_3': 11.0, 'atom_4': 2.0, 'atom_5': 10.0, 'atom_6': 5.0,
            'atom_7': 2.0, 'atom_8': 8.0, 'atom_9': 10.0, 'atom_10': 3.0
        })
        expected_groupings = [
            ['atom_2', 'atom_3', 'atom_10'],
            ['atom_4', 'atom_5', 'atom_7', 'atom_9'],
            ['atom_8'],
            ['atom_6'],
            ['atom_1']
        ]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_groupings_equal(expected_groupings, subjobs)

    def test_grouping_makes_atoms_with_no_timing_as_separate_subjobs(self):
        new_atoms = ['atom_0', 'atom_1']
        old_atoms_with_times = {}
        expected_number_of_subjobs = 2

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')

        subjobs = atom_grouper.groupings()
        self.assertEquals(expected_number_of_subjobs, len(subjobs))

    def test_grouping_defaults_to_atom_grouper_when_no_timing_data_exists(self):
        num_atoms = 1000
        max_executors = 2
        new_atoms = []

        for i in range(num_atoms):
            new_atoms.append('atom_' + str(i))
        old_atoms_with_times = {}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, max_executors, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self.assertEquals(num_atoms, len(subjobs))

    def test_groupings_data_set_2(self):
        new_atoms = ['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5']
        old_atoms_with_times = dict({
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        })
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3', 'atom_4', 'atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_groupings_equal(expected_groupings, subjobs)

    def test_groupings_data_set_3(self):
        new_atoms = ['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5']
        old_atoms_with_times = dict({
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        })
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3'], ['atom_4', 'atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_groupings_equal(expected_groupings, subjobs)

    def test_groupings_data_set_4(self):
        new_atoms = ['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5']
        old_atoms_with_times = dict({
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        })
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3'], ['atom_4'], ['atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 5, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_groupings_equal(expected_groupings, subjobs)

    def test_groupings_maintains_project_directory_in_returned_atoms(self):
        new_atoms = [
            '/var/clusterrunner/repos/scm/atom_1',
            '/var/clusterrunner/repos/scm/atom_2',
            '/var/clusterrunner/repos/scm/atom_3'
        ]
        old_atoms_with_times = dict({'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 100.0})
        expected_groupings = [
            ['/var/clusterrunner/repos/scm/atom_1'],
            ['/var/clusterrunner/repos/scm/atom_2'],
            ['/var/clusterrunner/repos/scm/atom_3']
        ]
        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, '/var/clusterrunner/repos')
        subjobs = atom_grouper.groupings()

        self._assert_groupings_equal(expected_groupings, subjobs)

    def _assert_coalesced_contents(self, coalesced_atoms_with_historic_times, expected_atom_time_values):
        """
        Assert that coalesced_atoms_with_historic_times matches expected_atom_time_values

        :type coalesced_atoms_with_historic_times: list[list[str, float]]
        :type expected_atom_time_values: dict[str, float]
        """
        self.assertEquals(len(coalesced_atoms_with_historic_times), len(expected_atom_time_values))

        for atom_time_pair in coalesced_atoms_with_historic_times:
            atom = atom_time_pair[0]
            time = atom_time_pair[1]
            self.assertTrue(atom_time_pair[0] in expected_atom_time_values, 'No entry for Atom: ' + atom + ' found')

            if atom in expected_atom_time_values:
                self.assertEquals(time, expected_atom_time_values[atom], 'Incorrect time for atom ' + atom)

    def _assert_groupings_equal(self, expected, actual):
        """
        Assert that the two return subjob groupings are equivalent. The top-level ordering of the lists matters,
        but the inner list ordering does not matter.

        :param expected:
        :type expected: list[list[str]]
        :param actual:
        :type actual: list[list[str]]
        """
        self.assertEquals(len(expected), len(actual), 'Incorrect number of subjobs created!')

        for i in range(len(actual)):
            self.assertEquals(sorted(expected[i]), sorted(actual[i]))
