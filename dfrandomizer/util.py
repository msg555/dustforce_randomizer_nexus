"""
Misc utility methods used within dfrandomizer codebase.
"""
import argparse
import contextlib
import logging
import os
import tempfile


@contextlib.contextmanager
def open_and_swap(filename, mode="w+b", buffering=-1, encoding=None, newline=None):
    """
    Utility method for writing a file "atomically" by writing to a temporary
    file and atomically relinking the file after the write completes. This
    ensures if the script is interrupted a partial write will not be done.
    """
    fd, tmppath = tempfile.mkstemp(
        dir=os.path.dirname(filename) or ".",
        text="b" not in mode,
    )
    try:
        fh = open(
            fd,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            newline=newline,
            closefd=False,
        )
        yield fh
        os.rename(tmppath, filename)
        tmppath = None
    finally:
        if fh is not None:
            fh.close()
        os.close(fd)
        if tmppath is not None:
            os.unlink(tmppath)


class ArgumentParser(argparse.ArgumentParser):
    """
    Wrapper around argparse.ArgumentParser that adds some additional
    flags automatically.
    """

    def parse_args(self, *args, **kwargs):
        """Adds a verbose flag and setups up the logging level based on
        the level of verbosity requested. Otherwise behaves like a normal
        call to parse_args().
        """

        self.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
        )
        args = super().parse_args(*args, **kwargs)

        log_level = logging.WARN
        if args.verbose > 1:
            log_level = logging.DEBUG
        elif args.verbose:
            log_level = logging.INFO
        logging.basicConfig(
            format="%(levelname)s: %(message)s",
            level=log_level,
        )

        del args.verbose
        return args
