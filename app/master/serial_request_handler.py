import json
import os

from app.master.atom_grouper import AtomGrouper
from app.master.atomizer import AtomizerError
from app.master.build_request import BuildRequest
from app.master.subjob import Subjob
from app.master.time_based_atom_grouper import TimeBasedAtomGrouper
from app.util.log import get_logger


class SerialRequestHandler(object):

    def __init__(self):
        self._logger = get_logger(__name__)

    def handle_request(self, build):
        """
        Prepare a Build to be distributed across slaves.

        :param build: the Build instance to be prepared to be distributed across slaves
        :type build: Build
        """
        build_id = build.build_id()
        build_request = build.build_request
        if not isinstance(build_request, BuildRequest):
            raise RuntimeError('Build {} has no associated request object.'.format(build_id))

        self._logger.info('Fetching project for build {}.', build_id)
        build.project_type.fetch_project()

        self._logger.info('Successfully fetched project for build {}.', build_id)
        job_config = build.project_type.job_config()

        if job_config is None:
            build.mark_failed('Build failed while trying to parse cluster_runner.yaml.')
            return

        subjobs = self._compute_subjobs_for_build(build_id, job_config, build.project_type)
        build.prepare(subjobs, job_config)

    def _compute_subjobs_for_build(self, build_id, job_config, project_type):
        """

        :type build_id: int
        :type job_config: JobConfig
        :param project_type: the docker, directory, or git repo project_type that this build is running in
        :type project_type: project_type.project_type.ProjectType
        :rtype: list[Subjob]
        """
        atoms_list = job_config.atomizer.atomize_in_project(project_type)

        # Group the atoms together using some grouping strategy
        timing_file_path = project_type.timing_file_path(job_config.name)
        grouped_atoms = self._grouped_atoms(
            atoms_list,
            job_config.max_executors,
            timing_file_path,
            project_type.project_directory
        )

        # Generate subjobs for each group of atoms
        subjobs = []
        for subjob_id in range(len(grouped_atoms)):
            atoms = grouped_atoms[subjob_id]
            subjobs.append(Subjob(build_id, subjob_id, project_type, job_config, atoms))
        return subjobs

    def _grouped_atoms(self, atoms, max_executors, timing_file_path, project_directory):
        """
        Return atoms that are grouped for optimal CI performance.

        If a timing file exists, then use the TimeBasedAtomGrouper.
        If not, use the default AtomGrouper (groups each atom into its own subjob).

        :param atoms: all of the atoms to be run this time
        :type atoms: list[str]
        :param max_executors: the maximum number of executors for this build
        :type max_executors: int
        :param timing_file_path: path to where the timing data file would be stored (if it exists) for this job
        :type timing_file_path: str
        :type project_directory: str
        :return: the grouped atoms (in the form of list of lists of strings)
        :rtype: list[list[str]]
        """
        atom_time_map = None

        if os.path.isfile(timing_file_path):
            with open(timing_file_path, 'r') as json_file:
                try:
                    atom_time_map = json.load(json_file)
                except ValueError:
                    self._logger.warning('Failed to load timing data from file that exists {}', timing_file_path)

        if atom_time_map is not None and len(atom_time_map) > 0:
            atom_grouper = TimeBasedAtomGrouper(atoms, max_executors, atom_time_map, project_directory)
        else:
            atom_grouper = AtomGrouper(atoms, max_executors)

        return atom_grouper.groupings()


