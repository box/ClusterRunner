#!/bin/sh

# A pass-through wrapper script around ssh that allows setting additional arguments via environment variable. It can be
# used as the target of $GIT_SSH to enable setting git's ssh options in a script.

GIT_SSH_ARGS=${GIT_SSH_ARGS:-""}  # default to "" (no injected args)
ssh ${GIT_SSH_ARGS} $@
