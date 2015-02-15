from test.framework.pylint.clusterrunner_raw_checker import ClusterRunnerRawChecker


def register(linter):
    """
    Register custom lint checkers with pylint. Any new checkers should also be registered here.
    """
    linter.register_checker(ClusterRunnerRawChecker(linter))
