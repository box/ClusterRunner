from unittest.mock import Mock
from app.master.atom import Atom
from app.master.time_based_atom_grouper import TimeBasedAtomGrouper, _AtomTimingDataError
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestTimeBasedAtomGrouper(BaseUnitTestCase):
    def _mock_atoms(self, command_strings):
        atom_spec = Atom('key', 'val')
        return [Mock(spec_set=atom_spec, command_string=cmd) for cmd in command_strings]

    def test_coalesce_new_atoms_with_no_atom_times(self):
        new_atoms = self._mock_atoms(['atom_1', 'atom_2', 'atom_3'])
        old_atoms_with_times = {}
        project_directory = 'some_project_directory'

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, project_directory)

        with self.assertRaises(_AtomTimingDataError):
            atom_grouper._set_expected_atom_times(new_atoms, old_atoms_with_times, project_directory)

    def test_coalesce_new_atoms_with_all_atom_times(self):
        new_atoms = self._mock_atoms(['atom_1', 'atom_2', 'atom_3'])
        old_atoms_with_times = {'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0}
        expected_contents = {'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        total_time = atom_grouper._set_expected_atom_times(new_atoms, old_atoms_with_times, 'some_project_directory')

        self.assertEquals(total_time, 6.0)
        self._assert_coalesced_contents(new_atoms, expected_contents)

    def test_coalesce_new_atoms_with_some_atom_times(self):
        new_atoms = self._mock_atoms(['atom_2', 'atom_3', 'atom_4', 'atom_5'])
        old_atoms_with_times = {'atom_1': 1.0, 'atom_2': 2.0, 'atom_3': 3.0}
        expected_contents = {'atom_2': 2.0, 'atom_3': 3.0, 'atom_4': 3.0, 'atom_5': 3.0}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        total_time = atom_grouper._set_expected_atom_times(new_atoms, old_atoms_with_times, 'some_project_directory')

        self.assertEquals(total_time, 11.0)
        self._assert_coalesced_contents(new_atoms, expected_contents)

    def test_groupings_data_set_1(self):
        new_atoms = self._mock_atoms([
            'atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5', 'atom_6', 'atom_7', 'atom_8', 'atom_9', 'atom_10'])
        old_atoms_with_times = {
            'atom_1': 1.0, 'atom_2': 10.0, 'atom_3': 11.0, 'atom_4': 2.0, 'atom_5': 10.0, 'atom_6': 5.0,
            'atom_7': 2.0, 'atom_8': 8.0, 'atom_9': 10.0, 'atom_10': 3.0
        }
        expected_groupings = [
            ['atom_2', 'atom_3', 'atom_10'],
            ['atom_4', 'atom_5', 'atom_7', 'atom_9'],
            ['atom_8'],
            ['atom_6'],
            ['atom_1']
        ]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_subjobs_match_expected_groupings(subjobs, expected_groupings)

    def test_grouping_makes_atoms_with_no_timing_as_separate_subjobs(self):
        new_atoms = self._mock_atoms(['atom_0', 'atom_1'])
        old_atoms_with_times = {}
        expected_number_of_subjobs = 2

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')

        subjobs = atom_grouper.groupings()
        self.assertEquals(expected_number_of_subjobs, len(subjobs))

    def test_grouping_defaults_to_atom_grouper_when_no_timing_data_exists(self):
        num_atoms = 1000
        max_executors = 2
        new_atoms = self._mock_atoms(['atom_{}'.format(i) for i in range(num_atoms)])
        old_atoms_with_times = {}

        atom_grouper = TimeBasedAtomGrouper(new_atoms, max_executors, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self.assertEquals(num_atoms, len(subjobs))

    def test_groupings_data_set_2(self):
        new_atoms = self._mock_atoms(['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5'])
        old_atoms_with_times = {
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        }
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3', 'atom_4', 'atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_subjobs_match_expected_groupings(subjobs, expected_groupings)

    def test_groupings_data_set_3(self):
        new_atoms = self._mock_atoms(['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5'])
        old_atoms_with_times = {
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        }
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3'], ['atom_4', 'atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 2, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_subjobs_match_expected_groupings(subjobs, expected_groupings)

    def test_groupings_data_set_4(self):
        new_atoms = self._mock_atoms(['atom_1', 'atom_2', 'atom_3', 'atom_4', 'atom_5'])
        old_atoms_with_times = {
            'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 50.0, 'atom_4': 2.0, 'atom_5': 2.0
        }
        expected_groupings = [['atom_1'], ['atom_2'], ['atom_3'], ['atom_4'], ['atom_5']]

        atom_grouper = TimeBasedAtomGrouper(new_atoms, 5, old_atoms_with_times, 'some_project_directory')
        subjobs = atom_grouper.groupings()

        self._assert_subjobs_match_expected_groupings(subjobs, expected_groupings)

    def test_groupings_maintains_project_directory_in_returned_atoms(self):
        new_atoms = self._mock_atoms([
            '/var/clusterrunner/repos/scm/atom_1',
            '/var/clusterrunner/repos/scm/atom_2',
            '/var/clusterrunner/repos/scm/atom_3'
        ])
        old_atoms_with_times = {'atom_1': 100.0, 'atom_2': 100.0, 'atom_3': 100.0}
        expected_groupings = [
            ['/var/clusterrunner/repos/scm/atom_1'],
            ['/var/clusterrunner/repos/scm/atom_2'],
            ['/var/clusterrunner/repos/scm/atom_3']
        ]
        atom_grouper = TimeBasedAtomGrouper(new_atoms, 3, old_atoms_with_times, '/var/clusterrunner/repos')
        subjobs = atom_grouper.groupings()

        self._assert_subjobs_match_expected_groupings(subjobs, expected_groupings)

    def _assert_coalesced_contents(self, coalesced_atoms_with_historic_times, expected_atom_time_values):
        """
        Assert that coalesced_atoms_with_historic_times matches expected_atom_time_values

        :type coalesced_atoms_with_historic_times: list[Atom]
        :type expected_atom_time_values: dict[str, float]
        """
        self.assertEquals(len(coalesced_atoms_with_historic_times), len(expected_atom_time_values))

        for atom in coalesced_atoms_with_historic_times:
            self.assertTrue(atom.command_string in expected_atom_time_values,
                            'No entry for Atom: ' + atom.command_string + ' found')

            if atom.command_string in expected_atom_time_values:
                self.assertEquals(atom.expected_time, expected_atom_time_values[atom.command_string],
                                  'Incorrect time for atom ' + atom.command_string)

    def _assert_subjobs_match_expected_groupings(self, actual_grouped_atoms, expected_groups):
        """
        Assert that the two return subjob groupings are equivalent. The top-level ordering of the lists matters,
        but the inner list ordering does not matter.

        :type actual_grouped_atoms: list[list[Atom]]
        :type expected_groups: list[list[str]]
        """
        actual_groups = [[atom.command_string for atom in atoms] for atoms in actual_grouped_atoms]
        self.assertEquals(len(expected_groups), len(actual_groups), 'Incorrect number of subjobs created!')

        for expected_group, actual_group in zip(expected_groups, actual_groups):
            self.assertCountEqual(expected_group, actual_group)
