import json
import os
from queue import Queue
from threading import Lock

from app.master.atom import Atom
from app.master.atom_grouper import AtomGrouper
from app.master.build_request import BuildRequest
from app.master.subjob import Subjob
from app.master.time_based_atom_grouper import TimeBasedAtomGrouper
from app.project_type.project_type import ProjectType
from app.util import analytics
from app.util.log import get_logger
from app.util.safe_thread import SafeThread


class BuildRequestHandler(object):
    """
    The BuildRequestHandler class is responsible for preparing a non-prepared build.

    Implementation notes:

    This class manages two critical Queue's in ClusterRunner: request_queue and builds_waiting_for_slaves.

    The request_queue is the queue of non-prepared Build instances that the BuildRequestHandler has
    yet to prepare. This queue is populated by the ClusterMaster instance.

    The builds_waiting_for_slaves queue is the queue of prepared Build instances that the
    BuildRequestHandler has completed build preparation for, and is waiting for the SlaveAllocator (a separate
    entity) to pull Builds from.

    All of the input of builds come through self.handle_build_request() calls, and all of the output
    of builds go through self.next_prepared_build() calls.
    """

    def __init__(self):
        self._logger = get_logger(__name__)
        self._builds_waiting_for_slaves = Queue()
        self._request_queue = Queue()
        self._request_queue_worker_thread = SafeThread(
            target=self._build_preparation_loop, name='RequestHandlerLoop', daemon=True)
        self._project_preparation_locks = {}

    def start(self):
        """
        Start the infinite loop that will accept unprepared builds and put them through build preparation.
        """
        if self._request_queue_worker_thread.is_alive():
            raise RuntimeError('Error: build request handler loop was asked to start when its already running.')
        self._request_queue_worker_thread.start()

    def handle_build_request(self, build):
        """
        :param build: the requested build
        :type build: Build
        """
        self._request_queue.put(build)
        analytics.record_event(analytics.BUILD_REQUEST_QUEUED, build_id=build.build_id(),
                               log_msg='Queued request for build {build_id}.')

    def next_prepared_build(self):
        """
        Get the next build that has successfully completed build preparation.

        This is a blocking call--if there are no more builds that have completed build preparation and this
        method gets invoked, the execution will hang until the next build has completed build preparation.

        :rtype: Build
        """
        return self._builds_waiting_for_slaves.get()

    def _build_preparation_loop(self):
        """
        Grabs a build off the request_queue (populated by self.handle_build_request()), prepares it,
        and puts that build onto the self.builds_waiting_for_slaves queue.
        """
        while True:
            build = self._request_queue.get()
            project_id = build.project_type.project_id()

            if project_id not in self._project_preparation_locks:
                self._logger.info('Creating project lock [{}] for build {}', project_id, str(build.build_id()))
                self._project_preparation_locks[project_id] = Lock()

            project_lock = self._project_preparation_locks[project_id]
            SafeThread(
                target=self._prepare_build_async,
                name='Bld{}-PreparationThread'.format(build.build_id()),
                args=(build, project_lock)
            ).start()

    def _prepare_build_async(self, build, project_lock):
        """
        :type build: Build
        :type project_lock: Lock
        """
        self._logger.info('Build {} is waiting for the project lock', build.build_id())

        with project_lock:
            self._logger.info('Build {} has acquired project lock', build.build_id())
            analytics.record_event(analytics.BUILD_PREPARE_START, build_id=build.build_id(),
                                   log_msg='Build preparation loop is handling request for build {build_id}.')
            try:
                self._prepare_build(build)
                if not build.has_error:
                    analytics.record_event(analytics.BUILD_PREPARE_FINISH, build_id=build.build_id(), is_success=True,
                                           log_msg='Build {build_id} successfully prepared and waiting for slaves.')
                    self._builds_waiting_for_slaves.put(build)
            except Exception as ex:  # pylint: disable=broad-except
                build.mark_failed(str(ex))
                self._logger.exception('Could not handle build request for build {}.'.format(build.build_id()))
                analytics.record_event(analytics.BUILD_PREPARE_FINISH, build_id=build.build_id(), is_success=False)

    def _prepare_build(self, build):
        """
        Prepare a Build to be distributed across slaves.

        :param build: the Build instance to be prepared to be distributed across slaves
        :type build: Build
        """
        build_id = build.build_id()
        build_request = build.build_request

        if not isinstance(build_request, BuildRequest):
            raise RuntimeError('Build {} has no associated request object.'.format(build_id))

        project_type = build.project_type
        if not isinstance(project_type, ProjectType):
            raise RuntimeError('Build {} has no project set.'.format(build_id))

        self._logger.info('Fetching project for build {}.', build_id)
        project_type.fetch_project()

        self._logger.info('Successfully fetched project for build {}.', build_id)
        job_config = project_type.job_config()

        if job_config is None:
            build.mark_failed('Build failed while trying to parse clusterrunner.yaml.')
            return

        subjobs = self._compute_subjobs_for_build(build_id, job_config, project_type)
        build.prepare(subjobs, job_config)

    def _compute_subjobs_for_build(self, build_id, job_config, project_type):
        """
        :type build_id: int
        :type job_config: JobConfig
        :param project_type: the directory, or git repo project_type that this build is running in
        :type project_type: project_type.project_type.ProjectType
        :rtype: list[Subjob]
        """
        # Users can override the list of atoms to be run in this build. If the atoms_override
        # was specified, we can skip the atomization step and use those overridden atoms instead.
        if project_type.atoms_override is not None:
            atoms_string_list = project_type.atoms_override
            atoms_list = [Atom(atom_string_value) for atom_string_value in atoms_string_list]
        else:
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
            # The atom id's aren't calculated until it's been assigned grouped in a subjob.
            for idx, atom in enumerate(atoms):
                atom.id = idx
            subjobs.append(Subjob(build_id, subjob_id, project_type, job_config, atoms))
        return subjobs

    def _grouped_atoms(self, atoms, max_executors, timing_file_path, project_directory):
        """
        Return atoms that are grouped for optimal CI performance.

        If a timing file exists, then use the TimeBasedAtomGrouper.
        If not, use the default AtomGrouper (groups each atom into its own subjob).

        :param atoms: all of the atoms to be run this time
        :type atoms: list[app.master.atom.Atom]
        :param max_executors: the maximum number of executors for this build
        :type max_executors: int
        :param timing_file_path: path to where the timing data file would be stored (if it exists) for this job
        :type timing_file_path: str
        :type project_directory: str
        :return: the grouped atoms (in the form of list of lists of strings)
        :rtype: list[list[app.master.atom.Atom]]
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
