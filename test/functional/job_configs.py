from test.framework.functional.fs_item import File, Directory


# These are the files that we expect to be present in every atom artifact directory.
DEFAULT_ATOM_FILES = [
    File('clusterrunner_command'),
    File('clusterrunner_console_output'),
    File('clusterrunner_exit_code'),
    File('clusterrunner_time'),
]


class FunctionalTestJobConfig(object):
    def __init__(self, config, expected_to_fail, expected_num_subjobs, expected_num_atoms,
                 expected_artifact_contents=None, expected_project_dir_contents=None):
        self.config = config
        self.expected_to_fail = expected_to_fail
        self.expected_num_subjobs = expected_num_subjobs
        self.expected_num_atoms = expected_num_atoms
        self.expected_artifact_contents = expected_artifact_contents
        self.expected_project_dir_contents = expected_project_dir_contents


# This is a very basic job where each atom just creates a simple text file.
BASIC_JOB = FunctionalTestJobConfig(
    config={
        'posix': """
BasicJob:
    commands:
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: seq 0 4 | xargs -I {} echo "This is atom {}"

""",
        'nt': """
BasicJob:
    commands:
        - echo !TOKEN!> !ARTIFACT_DIR!\\result.txt
    atomizers:
        - TOKEN: FOR /l %n in (0,1,4) DO @echo This is atom %n
""",
    },
    expected_to_fail=False,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[
        Directory('artifact_0_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 0\n')]),
        Directory('artifact_1_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 1\n')]),
        Directory('artifact_2_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 2\n')]),
        Directory('artifact_3_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 3\n')]),
        Directory('artifact_4_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 4\n')]),
    ],
)


# This is a very basic job, but one of the atoms will fail with non-zero exit code.
BASIC_FAILING_JOB = FunctionalTestJobConfig(
    config={
        'posix': """
BasicFailingJob:
    commands:
        - if [ "$TOKEN" = "This is atom 3" ]; then exit 1; fi
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: seq 0 4 | xargs -I {} echo "This is atom {}"

""",
        'nt': """
BasicFailingJob:
    commands:
        - IF "!TOKEN!" == "This is atom 3" (EXIT 1) ELSE (echo !TOKEN!> !ARTIFACT_DIR!\\result.txt)
    atomizers:
        - TOKEN: FOR /l %n in (0,1,4) DO @echo This is atom %n
""",
    },
    expected_to_fail=True,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[
        Directory('artifact_0_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 0\n')]),
        Directory('artifact_1_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 1\n')]),
        Directory('artifact_2_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 2\n')]),
        Directory('artifact_3_0', DEFAULT_ATOM_FILES),
        Directory('artifact_4_0', DEFAULT_ATOM_FILES + [File('result.txt', contents='This is atom 4\n')]),
        File('failures.txt', contents='artifact_3_0'),
    ],
)


# This is a more complex job. Each step (setup_build, commands, teardown_build) depends on the previous steps. This
# config also includes short sleeps to help tease out race conditions around setup and teardown timing.
JOB_WITH_SETUP_AND_TEARDOWN = FunctionalTestJobConfig(
    config={
        'posix': """
JobWithSetupAndTeardown:
    setup_build:
        - echo "Doing build setup."
        - sleep 1
        - echo "setup." >> $PROJECT_DIR/build_setup.txt

    commands:
        - echo "Doing subjob $SUBJOB_NUMBER."
        - sleep 1
        - MY_SUBJOB_FILE=$PROJECT_DIR/subjob_file_${SUBJOB_NUMBER}.txt
        - echo "subjob $SUBJOB_NUMBER." >> $MY_SUBJOB_FILE

    atomizers:
        - SUBJOB_NUMBER: seq 1 3

    teardown_build:
        - echo "Doing build teardown."
        - sleep 1
        - echo "teardown." >> $PROJECT_DIR/build_teardown.txt

""",
        'nt': """
        # sleep 1 is replaced by ping 127.0.0.1 -n 2 to generate a small amount of delay.
        # I didn't use 'timeout /t 1' since it would fail with "ERROR: Input redirection is not supported,
        # exiting the process immediately."
JobWithSetupAndTeardown:
    setup_build:
        - echo Doing build setup.
        - ping 127.0.0.1 -n 2 >nul
        - echo setup.>> !PROJECT_DIR!\\build_setup.txt

    commands:
        - echo Doing subjob !SUBJOB_NUMBER!.
        - ping 127.0.0.1 -n 2 >nul
        - set MY_SUBJOB_FILE=!PROJECT_DIR!\\subjob_file_!SUBJOB_NUMBER!.txt
        - echo subjob !SUBJOB_NUMBER!.>> !MY_SUBJOB_FILE!

    atomizers:
        - SUBJOB_NUMBER: FOR /l %n in (1,1,3) DO @echo %n

    teardown_build:
        - echo Doing build teardown.
        - ping 127.0.0.1 -n 2 >nul
        - echo teardown.>> !PROJECT_DIR!\\build_teardown.txt
""",
    },
    expected_to_fail=False,
    expected_num_subjobs=3,
    expected_num_atoms=3,
    expected_project_dir_contents=[
        File('build_setup.txt', contents='setup.\n'),
        File('subjob_file_1.txt', contents='subjob 1.\n'),
        File('subjob_file_2.txt', contents='subjob 2.\n'),
        File('subjob_file_3.txt', contents='subjob 3.\n'),
        File('build_teardown.txt', contents='teardown.\n'),
    ],
)

# This is a very basic job where each atom just sleeps for 1 second.
JOB_WITH_SLEEPS = FunctionalTestJobConfig(
    config={
        'posix': """
BasicSleepingJob:
    commands:
        - sleep 1
    atomizers:
        - TOKEN: seq 0 4 | xargs -I {} echo "This is atom {}"

""",
        'nt': """
BasicSleepingJob:
    commands:
        - timeout 1 > NUL
    atomizers:
        - TOKEN: FOR /l %n in (0,1,4) DO @echo This is atom %n
""",
    },
    expected_to_fail=False,
    expected_num_subjobs=5,
    expected_num_atoms=5,
)

# This is a very basic job where each atom (total 90) just sleeps for 1 second.
JOB_WITH_SLEEPS_90SEC = FunctionalTestJobConfig(
    config={
        'posix': """
SleepingJob90Sec:
    commands:
        - sleep 1
    atomizers:
        - TOKEN: seq 0 90 | xargs -I {} echo "This is atom {}"

""",
        'nt': """
SleepingJob90Sec:
    commands:
        - timeout 1 > NUL
    atomizers:
        - TOKEN: FOR /l %n in (0,1,90) DO @echo This is atom %n
""",
    },
    expected_to_fail=False,
    expected_num_subjobs=90,
    expected_num_atoms=90,
)

# This is a very basic job where each atom (total 90) just sleeps for 1 second.
JOB_WITH_SLEEPING_ATOMIZER_90SEC = FunctionalTestJobConfig(
    config={
        'posix': """
SleepingAtomizerJob90Sec:
    commands:
        - echo $ATOM
    atomizers:
        - ATOM: echo "$$" > /tmp/atomizer_pid.txt; for x in $(seq 1 90); do sleep 1 && echo $x; done
""",
    },
    expected_to_fail=False,
    expected_num_subjobs=90,
    expected_num_atoms=90,
)

FAILING_SETUP_JOB = FunctionalTestJobConfig(
    config={
        'posix': """
FailingSetupJob:
    setup_build:
        - exit 1
    commands:
        - echo $TOKEN
    atomizers:
        - TOKEN: seq 0 4
""",
        'nt': """
FailingSetupJob:
    setup_build:
        - exit /b 1
    commands:
        - echo !TOKEN!
    atomizers:
        - TOKEN: seq 0 4
"""
    },
    expected_to_fail=True,
    expected_num_subjobs=5,
    expected_num_atoms=5
)
