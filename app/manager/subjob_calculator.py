import json
import os

from app.manager.atom import Atom
from app.manager.atom_grouper import AtomGrouper
from app.manager.subjob import Subjob
from app.manager.time_based_atom_grouper import TimeBasedAtomGrouper
from app.util import log


def compute_subjobs_for_build(build_id, job_config, project_type):
    """
    Calculate subjobs for a build.
    :type build_id: int
    :type job_config: JobConfig
    :param project_type: the project_type that the build is running in
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
    grouped_atoms = _grouped_atoms(
        atoms_list,
        job_config.max_executors,
        timing_file_path,
        project_type.project_directory
    )

    # Generate subjobs for each group of atoms
    subjobs = []
    for subjob_id, subjob_atoms in enumerate(grouped_atoms):
        # The atom id isn't calculated until the atom has been grouped into a subjob.
        for atom_id, atom in enumerate(subjob_atoms):
            atom.id = atom_id
        subjobs.append(Subjob(build_id, subjob_id, project_type, job_config, subjob_atoms))
    return subjobs


def _grouped_atoms(atoms, max_executors, timing_file_path, project_directory):
    """
    Return atoms that are grouped for optimal CI performance.

    If a timing file exists, then use the TimeBasedAtomGrouper.
    If not, use the default AtomGrouper (groups each atom into its own subjob).

    :param atoms: all of the atoms to be run this time
    :type atoms: list[app.manager.atom.Atom]
    :param max_executors: the maximum number of executors for this build
    :type max_executors: int
    :param timing_file_path: path to where the timing data file would be stored (if it exists) for this job
    :type timing_file_path: str
    :type project_directory: str
    :return: the grouped atoms (in the form of list of lists of strings)
    :rtype: list[list[app.manager.atom.Atom]]
    """
    atom_time_map = None

    if os.path.isfile(timing_file_path):
        with open(timing_file_path, 'r') as json_file:
            try:
                atom_time_map = json.load(json_file)
            except ValueError:
                logger = log.get_logger(__name__)
                logger.warning('Failed to load timing data from file that exists {}', timing_file_path)

    if atom_time_map is not None and len(atom_time_map) > 0:
        atom_grouper = TimeBasedAtomGrouper(atoms, max_executors, atom_time_map, project_directory)
    else:
        atom_grouper = AtomGrouper(atoms, max_executors)

    return atom_grouper.groupings()
