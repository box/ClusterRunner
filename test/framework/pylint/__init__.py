from test.framework.pylint.clusterrunner_token_checker import ClusterRunnerTokenChecker


def register(linter):
    """
    Register custom lint checkers with pylint. Any new checkers should also be registered here.
    """
    linter.register_checker(ClusterRunnerTokenChecker(linter))
