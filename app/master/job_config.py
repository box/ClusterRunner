

class JobConfig(object):
    def __init__(self, name, setup_build, teardown_build, command, atomizer, max_executors):
        """
        :type name: str
        :type setup_build: str | None
        :type teardown_build: str | None
        :type command: str
        :type atomizer: Atomizer
        :type max_executors: int | None
        """
        self.name = name
        self.setup_build = setup_build
        self.teardown_build = teardown_build
        self.command = command
        self.atomizer = atomizer
        self.max_executors = max_executors
