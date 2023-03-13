#!/usr/bin/python3


from subprocess import check_output, CalledProcessError, PIPE
from typing import List, Optional, Union
import argparse
import os
import sys


class GitEnv:

    def __init__(self, repo_path: str) -> None:
        self.repo_path = repo_path

        if not self.is_repo_valid():
            raise ValueError(f'{self.repo_path} is not a valid git repository path')

    @staticmethod
    def bytes_to_str(output: bytes) -> str:
        return output.decode('utf-8').strip()

    def cmd(self, cmd_args: List[str], binary_input: bytes = None) -> bytes:
        return check_output(cmd_args, cwd=self.repo_path, input=binary_input, stderr=PIPE)

    def is_repo_valid(self) -> bool:
        try:
            return 'true' == self.bytes_to_str(self.cmd(['git', 'rev-parse', '--is-inside-work-tree']))
        except:
            return False

    def diff(self, old_ref: str, new_ref: str) -> bytes:
        return self.cmd(['git', 'diff', '--no-color', '--binary', old_ref, new_ref])

    def apply(self, diff: bytes) -> None:
        self.cmd(['git', 'apply', '--index'], diff)

    def commit(self, message: str) -> None:
        self.cmd(['git', 'commit', '-m', message])

    def get_branch(self, reference: str = 'HEAD') -> str:
        result = self.bytes_to_str(self.cmd(['git', 'rev-parse', '--abbrev-ref', reference]))
        return result if result != 'HEAD' else ''

    def get_sha(self, reference: str = 'HEAD') -> str:
        return self.bytes_to_str(self.cmd(['git', 'rev-parse', reference]))

    def checkout(self, reference: str) -> None:
        self.cmd(['git', 'checkout', '--quiet', reference])

    def reset_hard(self, reference: str) -> None:
        self.cmd(['git', 'reset', '--hard', reference])


class CmdParser:

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(description='Squashes changes into a one commit.')
        self.parser.add_argument('target', help='destination branch/commit reference')
        self.parser.add_argument('-m', metavar='MESSAGE', help='custom squashed commit message')
        self.parser.add_argument('-p', metavar='REPO_PATH', default=os.getcwd(),
                                 help='specifies custom path to the repository if different than the working directory')
        self.parser.add_argument('-s', metavar='SOURCE_BRANCH', default='HEAD',
                                 help='specifies custom source branch if different than HEAD')
        self.parser.add_argument('-q', '--quiet', action='store_true', help='suppress log messages')
        self.args = self.parser.parse_args()

    @property
    def target(self) -> str:
        return self.args.target

    @property
    def source(self) -> str:
        return self.args.s

    @property
    def custom_message(self) -> Optional[str]:
        return self.args.m

    @property
    def repo_path(self) -> str:
        return self.args.p

    @property
    def verbose(self) -> str:
        return not self.args.quiet


class SquashOperation:

    def __init__(self, git: GitEnv, target_ref: str, source_ref: str, custom_message: Optional[str]) -> None:
        self.git = git
        self.target_ref = target_ref

        try:
            self.target_sha = git.get_sha(target_ref)
            self.source_sha = git.get_sha(source_ref)
            self.source_branch = git.get_branch(source_ref)
        except CalledProcessError as e:
            raise ValueError(f'{target_ref} and {source_ref} must be both valid git references')

        if not self.source_branch:
            raise ValueError(f'{source_ref} must be a branch')

        self.message = custom_message or f'Squashed {self.source_branch}'

    def perform(self) -> None:
        self.git.checkout(self.target_sha)
        self.git.apply(self.git.diff(self.target_sha, self.source_branch))
        self.git.commit(self.message)
        new_commit_sha = self.git.get_sha()
        self.git.checkout(self.source_branch)
        self.git.reset_hard(new_commit_sha)

    def revert(self) -> None:
        self.git.checkout(self.source_branch)
        self.git.reset_hard(self.source_sha)


class Logger:

    def __init__(self, turned_on: bool) -> None:
        self.turned_on = turned_on

    def log(self, message: Union[str, bytes], to_stderr: bool) -> None:
        if self.turned_on:
            stream = sys.stderr if to_stderr else sys.stdout
            if isinstance(message, bytes):
                message = GitEnv.bytes_to_str(message)
            print(message, file=stream)

    def info(self, message: Union[str, bytes]):
        self.log(message, to_stderr=False)

    def error(self, message: Union[str, bytes]):
        self.log(message, to_stderr=True)


if __name__ == '__main__':
    parser = CmdParser()
    logger = Logger(parser.verbose)

    try:
        git = GitEnv(parser.repo_path)
        squash = SquashOperation(git, parser.target, parser.source, parser.custom_message)
        squash.perform()
        logger.info(
            f'Successfully squashed {squash.source_branch} onto {squash.target_ref}\n'
            f'To revert changes call: git reset --hard {squash.source_sha}'
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except CalledProcessError as e:
        squash.revert()
        logger.error(e.stderr)
        sys.exit(e.returncode)
