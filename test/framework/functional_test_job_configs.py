

class FunctionalTestJobConfig(object):
    def __init__(self, config, expected_to_fail, expected_num_subjobs, expected_num_atoms, expected_artifact_contents):
        self.config = config
        self.expected_to_fail = expected_to_fail
        self.expected_num_subjobs = expected_num_subjobs
        self.expected_num_atoms = expected_num_atoms
        self.expected_artifact_contents = expected_artifact_contents


# This is a very basic job where each atom just creates a simple text file.
BASIC_JOB = FunctionalTestJobConfig(
    config="""

BasicJob:
    commands:
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: printf 'This is atom %d\\n' {0..4}

""",
    expected_to_fail=False,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[
        [{'result.txt': 'This is atom 0\n'}],
        [{'result.txt': 'This is atom 1\n'}],
        [{'result.txt': 'This is atom 2\n'}],
        [{'result.txt': 'This is atom 3\n'}],
        [{'result.txt': 'This is atom 4\n'}],
    ],
)


# This is a very basic job, but one of the atoms will fail with non-zero exit code.
BASIC_FAILING_JOB = FunctionalTestJobConfig(
    config="""

BasicFailingJob:
    commands:
        - if [[ $TOKEN == *This\ is\ atom\ 3* ]]; then exit 1; fi
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: printf 'This is atom %d\\n' {0..4}

""",
    expected_to_fail=True,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[
        [{'result.txt': 'This is atom 0\n'}],
        [{'result.txt': 'This is atom 1\n'}],
        [{'result.txt': 'This is atom 2\n'}],
        [],
        [{'result.txt': 'This is atom 4\n'}],
    ],
)
