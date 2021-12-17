#!/usr/bin/env python3

import argparse
import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Union


class cd:
    """
    Change directories safely, go back to the previous CWD when exiting.

    @see https://stackoverflow.com/a/13197763/8846676
    """

    def __init__(self, new_path, dry_run=False):
        self.new_path = os.path.expanduser(new_path)
        self._dry_run = dry_run

    def __enter__(self):
        if not self._dry_run:
            self.saved_path = os.getcwd()
            os.chdir(self.new_path)

    def __exit__(self, etype, value, traceback):
        if not self._dry_run:
            os.chdir(self.saved_path)


def get_git_email(gitconfig_path: Union[Path, None] = None) -> Union[str, None]:
    """
    Get Git author username.

    Falls back to GIT_AUTHOR_EMAIL then to EMAIL then to None if user.email is
    not set in .gitconfig.
    """
    if gitconfig_path is None:
        gitconfig_path = Path.home() / ".gitconfig"

    config = configparser.ConfigParser()
    config.read(gitconfig_path)

    try:
        return config.get("user", "email")
    except configparser.NoOptionError:
        pass

    try:
        return os.environ["GIT_AUTHOR_EMAIL"]
    except KeyError:
        return os.environ.get("EMAIL")


def force_init_output(output_dir: Path) -> None:
    """Create or reinitialize a target `sync` repository.

    If the repository already exists, delete the entire existing git history.
    Otherwise, create the directory (and parents if necessary) and the repository.

    Args:
        output_dir: Path to to-be created or reinitialized repository.
    """
    if output_dir.is_dir():
        git_dir = output_dir / ".git"
        if git_dir.is_dir():
            shutil.rmtree(output_dir / ".git")
    else:
        output_dir.mkdir()

    with cd(output_dir):
        subprocess.run(
            [
                "git",
                "init",
            ],
            check=True,
        )
        # Create an empty file indicating this is a sync repo.
        info_file = Path(output_dir) / "sync_repo.dat"
        info_file.write_text("")

        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-am", "Initial commit"], check=True)


def validate_existing_output_repo(output_dir: Path) -> bool:
    """
    TODO:
    """
    if not output_dir.is_dir():
        return False

    git_dir = output_dir / ".git"
    if not git_dir.is_dir():
        return False

    # TODO: Proper logging here
    if not Path(output_dir, "sync_repo.dat").is_file():
        print(
            "This output repository doesn't appear to be dedicated to syncing contributions. Proceed with caution!"
        )

    return True


def commit_exists(output_dir: Path, sha: str) -> bool:
    """Check if a commit with subject `sha` exists in a repository.

    Args:
        output_dir: Path to git repository.
        sha: Subject line to search for.

    Returns:
        Whether 1 or more commits with subject line `sha` exist.
    """
    process = subprocess.run(
        [
            "git",
            "-C",
            str(output_dir.absolute()),
            "log",
            "--format=format:%f",
            f"--grep={sha}",
        ],
        capture_output=True,
    )
    return len(process.stdout.decode().strip())


def recreate_commits(identity: str, in_git_dir: Path, output_dir: Path) -> int:
    """Copy contributions from one local repository to another.

    Copy commit dates and times, but no actual data. This emulates as if the
    commit had actually occured, without writing any data to the repository.
    Copied commits' subject lines are the full hash of the source commit.

    Args:
        identity: Git identity to use when searching for and writing contributions.
                  Uses the same format as `git log --author`.
        in_git_dir: Path to root of source git repository.
        output_dir: Path to root of target git repository.

    Returns:
       The number of commits copied, excluding already copied commits.
    """
    process = subprocess.run(
        [
            "git",
            "-C",
            str(in_git_dir.absolute()),
            "log",
            "--format=format:%aD|%cD|%H",
            "--author",
            identity,
        ],
        capture_output=True,
        check=True,
    )

    num_copied = 0
    for commit in process.stdout.decode().split("\n"):
        try:
            author_timestamp, commit_timestamp, sha = commit.split("|")
        except ValueError:
            continue

        if commit_exists(output_dir, sha):
            # TODO: Do proper logging here.
            print(f"Commit for {sha} already exists. Skipping...", file=sys.stderr)
            continue

        command = [
            "git",
            "-C",
            str(output_dir.absolute()),
            "commit",
            "--allow-empty",
            "-m",
            sha,
        ]
        env = {
            **os.environ.copy(),
            "GIT_AUTHOR_DATE": author_timestamp,
            "GIT_COMITER_DATE": commit_timestamp,
        }
        subprocess.run(command, env=env, check=True)
        num_copied += 1

    return num_copied


def add_generic_arg(parsers: list[argparse.ArgumentParser], *args, **kwargs) -> None:
    """Apply adding an argument to multiple argparse subparses simultaneously."""
    for p in parsers:
        p.add_argument(*args, **kwargs)


def sync_github(cli_args) -> None:
    """Sync contribution from a GitHub user to a local repository."""
    raise NotImplementedError


def sync_gitlab(cli_args) -> None:
    """Sync contribution from a GitLab user to a local repository."""
    raise NotImplementedError


def sync_local(cli_args) -> None:
    """Sync contribution from a local repository to another local repository."""
    input_path = Path(cli_args.INPUT_REPO)
    output_path = cli_args.DESTINATION_REPO
    identity = cli_args.identity

    recreate_commits(identity, input_path, output_path)

    # TODO: Proper logging
    # print(f"Finished copying commits from {input_path} to {output_path}")


if __name__ == "__main__":
    # Argument parsing
    parser = argparse.ArgumentParser(
        description="Sync contributions between various Git hosting solutions."
    )
    subparsers = parser.add_subparsers(title="Data Sources", required=True)

    # Github subparser ---------------------------------------------------------
    parser_github = subparsers.add_parser(
        "github",
        help="Pull contributions from a GitHub account.",
    )

    # GitLab subparser ---------------------------------------------------------
    parser_gitlab = subparsers.add_parser(
        "gitlab",
        help="Pull contributions from a GitLab account",
    )

    # Local subparser ----------------------------------------------------------
    parser_local = subparsers.add_parser(
        "local",
        help="Pull contributions from an existing repository on disk.",
    )
    parser_local.add_argument("INPUT_REPO", help="Path to input repository.")
    parser_local.add_argument(
        "--identity",
        help="Git identity to use when finding commits. Same format as `git log --author`.",
    )

    # Generic arguments --------------------------------------------------------
    add_generic_arg(
        (parser_github, parser_gitlab, parser_local),
        "DESTINATION_REPO",
        type=str,
        help="Path to repository for newly created dummy commits.",
    )
    add_generic_arg(
        (parser_github, parser_gitlab, parser_local),
        "-f",
        "--force",
        action="store_true",
        help="""\
        Overwrite an existing destination repository or create the
        directories necessary for the supplied destination directory.
        DANGER: Will delete an existing git repository.
        """,
    )
    add_generic_arg(
        (parser_github, parser_gitlab, parser_local),
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all non-error related outputs.",
    )

    # Link subcommands to corresponding functions.
    parser_github.set_defaults(func=sync_github)
    parser_gitlab.set_defaults(func=sync_gitlab)
    parser_local.set_defaults(func=sync_local)
    args = parser.parse_args()

    # TODO: Use log library for this
    QUIET = args.quiet

    args.DESTINATION_REPO = Path(args.DESTINATION_REPO)
    if args.force:
        force_init_output(args.DESTINATION_REPO)
    if args.identity is None:
        args.identity = get_git_email()

    validate_existing_output_repo(args.DESTINATION_REPO)

    # Call the function associated with the subcommand.
    args.func(args)
