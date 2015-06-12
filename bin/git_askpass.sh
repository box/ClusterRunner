#!/bin/sh

# This script is a just a no-op dummy script that outputs nothing. It can be used as the target of $GIT_ASKPASS so that
# all git prompts will be automatically filled with an invalid empty response, causing all prompts to fail.
