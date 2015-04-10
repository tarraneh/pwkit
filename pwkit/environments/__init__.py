# -*- mode: python; coding: utf-8 -*-
# Copyright 2015 Peter Williams <peter@newton.cx> and collaborators.
# Licensed under the MIT License.

"""pwkit.environments - working with external software environments

Classes:

  Environment - base class for launching programs in an external environment.

Submodules:

  heasoft - HEAsoft
  sas     - SAS

Functions:

  prepend_environ_path - Prepend into a $PATH in an environment dict.
  prepend_path         - Prepend text into a $PATH-like environment variable.
  user_data_path       - Generate paths for storing miscellaneous user data.

Standard usage is to create an `Environment` instance, then use its
`launch(argv, ...)` method to run programs in the specified environment.
`launch()` returns a `subprocess.Popen` instance that can be used in the
standard ways.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

"""For reference: the Python docs state that Python automatically decodes
Unicode environment variables as UTF-8 on non-Windows, so we don't need to be
crazy about bytes-ifying values.

"""
__all__ = (b'Environment prepend_environ_path prepend_path user_data_path').split ()

import os, subprocess, sys

from .. import cli


class Environment (object):
    def modify_environment (self, environ):
        """Modify the passed-in dictionary of environment variables to be suitable for
        executing programs in this software environment. Make sure to copy
        os.environ() if you don't want to modify it for the current process.

        """
        raise NotImplementedError ()


    def _preexec (self, env, **kwargs):
        pass


    def launch (self, args, stdin=None, stdout=None, stderr=None,
                close_fds=False, env=None, shell=False, cwd=None, **kwargs):
        if env is None:
            env = os.environ

        env = self.modify_environment (env.copy ())
        self._preexec (env, **kwargs)
        return subprocess.Popen (args, stdin=stdin, stdout=stdout,
                                 stderr=stderr, close_fds=close_fds,
                                 env=env, shell=shell, cwd=cwd)

    def execvpe (self, argv, env=None, **kwargs):
        if env is None:
            env = os.environ

        env = self.modify_environment (env.copy ())
        self._preexec (env, **kwargs)
        # unlike subprocess.Popen, execvpe doesn't use the new path to find
        # the program. But we're about to replace ourselves with the new
        # program, so no worries about mutating os.environ. If the exec fails
        # the mutation will remain, though.
        os.environ[b'PATH'] = env['PATH']
        os.execvpe (argv[0], argv, env)


def prepend_path (orig, text, pathsep=os.pathsep):
    """Returns a $PATH-like environment variable with `text` prepended. `orig` is
    the original variable value, or None. `pathsep` is the character
    separating path elements, defaulting to `os.pathsep`.

    Example:

    newpath = cli.prepend_path (oldpath, '/mypackage/bin')

    See also `prepend_environ_path`.

    """
    if orig is None:
        orig = ''
    if not len (orig):
        return text
    return ''.join ([text, pathsep, orig])


def prepend_environ_path (env, name, text, pathsep=os.pathsep):
    """Prepend `text` into a $PATH-like environment variable. `env` is a
    dictionary of environment variables and `name` is the variable name.
    `pathsep` is the character separating path elements, defaulting to
    `os.pathsep`. The variable will be created if it is not already in `env`.
    Returns `env`.

    Example:

    prepend_environ_path (env, b'PATH', b'/mypackage/bin')
    """
    env[name] = prepend_path (env.get (name), text, pathsep=pathsep)
    return env


def _make_user_data_pather ():
    datadir = os.environ.get (b'XDG_DATA_HOME',
                              os.path.expanduser ('~/.local/share'))

    def pathfunc (*args):
        return os.path.join (datadir, *args)

    return pathfunc

user_data_path = _make_user_data_pather ()


# Command-line access

def _default_env_commandline (envname, module, argv):
    for name in dir (module):
        v = getattr (module, name)
        if v is not Environment and issubclass (v, Environment):
            envclass = v
            break
    else:
        cli.die ('internal error: cannot identify environment class for %s',
                 envname)

    if len (argv) < 3 or argv[1] in ('-h', '--help'):
        print ('''usage: %s exec <program> [args...]

Run a program in the %s environment. This is a generic launcher,
and the only supported operation is "exec".''' % (argv[0], envname))
        return

    if argv[1] != 'exec':
        cli.die ('usage: %s exec <program> [args...]' % argv[0])

    progargv = argv[2:]
    envclass ().execvpe (progargv)


def commandline (argv=sys.argv):
    cli.propagate_sigint ()
    cli.backtrace_on_usr1 ()
    cli.unicode_stdio ()

    if len (argv) < 2 or argv[1] in ('-h', '--help'):
        print ('''usage: pkenvtool <environment> [args...]

Where acceptable "args" depend on the environment in question.''')
        return

    envname = argv[1]
    if not len (envname) or envname[0] == '.':
        cli.die ('illegal environment name %r', envname)

    from importlib import import_module

    try:
        envmod = import_module ('.' + envname, package=__package__)
    except StandardError:
        cli.die ('unable to load module for environment %r', envname)

    modargv = ['pkenvtool ' + argv[1]] + argv[2:]

    if hasattr (envmod, 'commandline'):
        envmod.commandline (modargv)
    else:
        _default_env_commandline (envname, envmod, modargv)
