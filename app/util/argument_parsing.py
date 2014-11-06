import argparse


class ClusterRunnerArgumentParser(argparse.ArgumentParser):
    """
    This is a custom argument parser that gives us more control over the parsing behavior and help documentation output.

    This parser automatically splits required arguments and optional arguments into separate argument groups. This
    causes the help text to display these as two separate sections, making it much clearer which are optional and which
    are required. (Default is to list all but postitional arguments as "optional" even if they're required.)
    """
    def __init__(self, *args, **kwargs):
        # we will manually add the "help" argument so that we can explicitly put it in the "optional" argument group
        should_add_help = kwargs.pop('add_help', True)
        super().__init__(*args, add_help=False, **kwargs)

        self._required_arg_group = self.add_argument_group('required arguments')
        self._optional_arg_group = self.add_argument_group('optional arguments')
        if should_add_help:
            self._optional_arg_group.add_argument('-h', '--help', help='show this help message and exit', action='help')

    def add_argument(self, *args, **kwargs):
        """
        Instead of adding the argument directly to this parser, add it to either the required or optional argument
        groups. This causes help text to display required and optional arguments separately.
        """
        is_required = kwargs.get('required', False)
        target_arg_group = self._required_arg_group if is_required else self._optional_arg_group
        target_arg_group.add_argument(*args, **kwargs)

    def _get_option_tuples(self, option_string):
        """
        This method is overridden explicitly to disable argparse prefix matching. Prefix matching is an undesired
        default behavior as it creates the potential for unintended breaking changes just by adding a new command-line
        argument.

        For example, if a user uses the argument "--master" to specify a value for "--master-url", and later we add a
        new argument named "--master-port", that change will break the user script that used "--master".

        See: https://docs.python.org/3.4/library/argparse.html#argument-abbreviations-prefix-matching
        """
        # This if statement comes from the superclass implementation -- it precludes a code path in the superclass
        # that is responsible for checking for argument prefixes. The return value of an empty list is the way that
        # this method communicates no valid arguments were found.
        chars = self.prefix_chars
        if option_string[0] in chars and option_string[1] in chars:
            return []

        return super()._get_option_tuples(option_string)


class ClusterRunnerHelpFormatter(argparse.HelpFormatter):
    def _get_help_string(self, action):
        """
        Appends the default argument value to the help string for non-required args that have default values.

        This implementation is loosely based off of the argparse.ArgumentDefaultsHelpFormatter.
        """
        help_string = action.help
        if not action.required:
            if action.default not in (argparse.SUPPRESS, None):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    # using old string formatting style here because argparse internals use that
                    help_string += ' (default: %(default)s)'
        return help_string

    def _format_action_invocation(self, action):
        """
        Changes the default argument invocation string from, e.g.,:
            -r REQUEST_BODY, --request-body REQUEST_BODY
        to:
            -r/--request-body <REQUEST_BODY>
        """
        if action.option_strings:
            action_invocation_string = '/'.join(action.option_strings)
            if action.nargs != 0:
                default = self._get_default_metavar_for_optional(action)
                metavar_string = self._format_args(action, default)
                action_invocation_string = '{} {}'.format(action_invocation_string, metavar_string)
            return action_invocation_string

        return super()._format_action_invocation(action)

    def _get_default_metavar_for_optional(self, action):
        """
        Encloses metavars in angle brackets.
        """
        return '<{}>'.format(action.dest.upper())
