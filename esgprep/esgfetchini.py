#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
    :platform: Unix
    :synopsis: Toolbox to prepare ESGF data for publication.

"""

from esgprep import __version__
from esgprep._utils.help import *
from esgprep._utils.parser import *
from esgprep.fetchini import run


def get_args(args=None):
    """
    Returns parsed command-line arguments.

    """
    # Instantiate argument parser.
    main = CustomArgumentParser(
        prog='esgfetchini',
        description=PROGRAM_DESC['fetchini'],
        formatter_class=MultilineFormatter,
        add_help=False,
        epilog=EPILOG)
    main._optionals.title = OPTIONAL
    main._positionals.title = POSITIONAL
    main.add_argument(
        '-h', '--help',
        action='help',
        help=HELP)
    main.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s ({})'.format(__version__),
        help=VERSION_HELP)
    main.add_argument(
        '-i',
        metavar='$ESGINI_DIR',
        type=str,
        default=os.getenv('ESGINI_DIR', '/esg/config/esgcet'),
        help=INI_HELP)
    main.add_argument(
        '-l', '--log',
        metavar='CWD',
        type=str,
        const='{}/logs'.format(os.getcwd()),
        nargs='?',
        help=LOG_HELP)
    main.add_argument(
        '-d', '--debug',
        action='store_true',
        default=False,
        help=VERBOSE_HELP)
    main.add_argument(
        '-p', '--project',
        metavar='NAME',
        type=str,
        nargs='+',
        help=PROJECT_HELP['fetchini'])
    group = main.add_mutually_exclusive_group(required=False)
    group.add_argument(
        '-k',
        action='store_true',
        default=False,
        help=KEEP_HELP)
    group.add_argument(
        '-o',
        action='store_true',
        default=False,
        help=OVERWRITE_HELP)
    main.add_argument(
        '-b',
        metavar='one_version',
        choices=['one_version', 'keep_versions'],
        type=str,
        nargs='?',
        const='one_version',
        help=BACKUP_HELP)
    main.add_argument(
        '--gh-user',
        metavar='USERNAME',
        default=os.getenv('USERNAME', None),
        type=str,
        help=GITHUB_USER_HELP)
    main.add_argument(
        '--gh-password',
        metavar='$GH_PASSWORD',
        default=os.getenv('GH_PASSWORD', None),
        type=str,
        help=GITHUB_PASSWORD_HELP)
    main.add_argument(
        '--devel',
        action='store_true',
        default=False,
        help=DEVEL_HELP)
    group = main.add_mutually_exclusive_group(required=False)
    group.add_argument(
        '--color',
        action='store_true',
        help=COLOR_HELP)
    group.add_argument(
        '--no-color',
        action='store_true',
        help=NO_COLOR_HELP)

    # Return command-line parser & program name.
    return main.prog, main.parse_args(args)


def main(args=None):
    """
    Run main program

    """
    # Get command-line arguments
    prog, args = get_args(args)

    # Add program name as argument.
    setattr(args, 'prog', prog)

    # Run program
    run(args)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    main()
