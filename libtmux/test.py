"""Helper methods for libtmux and downstream libtmux libraries."""
import contextlib
import logging
import os
import random
import time
import warnings
from typing import Callable, Optional

from .exc import WaitTimeout

logger = logging.getLogger(__name__)

TEST_SESSION_PREFIX = "libtmux_"
RETRY_TIMEOUT_SECONDS = int(os.getenv("RETRY_TIMEOUT_SECONDS", 8))
RETRY_INTERVAL_SECONDS = float(os.getenv("RETRY_INTERVAL_SECONDS", 0.05))


class RandomStrSequence:
    def __init__(self, characters: str = "abcdefghijklmnopqrstuvwxyz0123456789_"):
        self.characters: str = characters

    def __iter__(self):
        return self

    def __next__(self):
        return "".join(random.sample(self.characters, k=8))


namer = RandomStrSequence()
current_dir = os.path.abspath(os.path.dirname(__file__))
example_dir = os.path.abspath(os.path.join(current_dir, "..", "examples"))
fixtures_dir = os.path.realpath(os.path.join(current_dir, "fixtures"))


def retry(seconds: float = RETRY_TIMEOUT_SECONDS) -> bool:
    """
    Retry a block of code until a time limit or ``break``.

    .. deprecated:: 0.12.0
          `retry` doesn't work, it will be removed in libtmux 0.13.0, it is replaced by
          `retry_until`, more info: https://github.com/tmux-python/libtmux/issues/368.

    Parameters
    ----------
    seconds : float
        Seconds to retry, defaults to ``RETRY_TIMEOUT_SECONDS``, which is
        configurable via environmental variables.

    Returns
    -------
    bool
        True if time passed since retry() invoked less than seconds param.

    Examples
    --------

    >>> while retry():
    ...     p = w.attached_pane
    ...     p.server._update_panes()
    ...     if p.current_path == pane_path:
    ...         break
    """
    warnings.warn(
        "retry() is being deprecated and will soon be replaced by retry_until()",
        DeprecationWarning,
    )
    return (lambda: time.time() < time.time() + seconds)()


def retry_until(
    fun: Callable,
    seconds: float = RETRY_TIMEOUT_SECONDS,
    *,
    interval: Optional[float] = RETRY_INTERVAL_SECONDS,
    raises: Optional[bool] = True,
) -> bool:
    """
    Retry a function until a condition meets or the specified time passes.

    Parameters
    ----------
    fun : callable
        A function that will be called repeatedly until it returns ``True``  or
        the specified time passes.
    seconds : float
        Seconds to retry. Defaults to ``8``, which is configurable via
        ``RETRY_TIMEOUT_SECONDS`` environment variables.
    interval : float
        Time in seconds to wait between calls. Defaults to ``0.05`` and is
        configurable via ``RETRY_INTERVAL_SECONDS`` environment variable.
    raises : bool
        Wether or not to raise an exception on timeout. Defaults to ``True``.

    Examples
    --------

    >>> def f():
    ...     p = w.attached_pane
    ...     p.server._update_panes()
    ...     return p.current_path == pane_path
    ...
    ... retry(f)

    In pytest:

    >>> assert retry(f, raises=False)
    """
    ini = time.time()

    while not fun():
        end = time.time()
        if end - ini >= seconds:
            if raises:
                raise WaitTimeout()
            else:
                return False
        time.sleep(interval)
    return True


def get_test_session_name(server, prefix=TEST_SESSION_PREFIX):
    """
    Faker to create a session name that doesn't exist.

    Parameters
    ----------
    server : :class:`libtmux.Server`
        libtmux server
    prefix : str
        prefix for sessions (e.g. ``libtmux_``). Defaults to
        ``TEST_SESSION_PREFIX``.

    Returns
    -------
    str
        Random session name guaranteed to not collide with current ones.
    """
    while True:
        session_name = prefix + next(namer)
        if not server.has_session(session_name):
            break
    return session_name


def get_test_window_name(session, prefix=TEST_SESSION_PREFIX):
    """
    Faker to create a window name that doesn't exist.

    Parameters
    ----------
    session : :class:`libtmux.Session`
        libtmux session
    prefix : str
        prefix for windows (e.g. ``libtmux_``). Defaults to
        ``TEST_SESSION_PREFIX``.

        ATM we reuse the test session prefix here.

    Returns
    -------
    str
        Random window name guaranteed to not collide with current ones.
    """
    while True:
        window_name = prefix + next(namer)
        if not session.find_where(window_name=window_name):
            break
    return window_name


@contextlib.contextmanager
def temp_session(server, *args, **kwargs):
    """
    Return a context manager with a temporary session.

    If no ``session_name`` is entered, :func:`get_test_session_name` will make
    an unused session name.

    The session will destroy itself upon closing with :meth:`Session.
    kill_session()`.

    Parameters
    ----------
    server : :class:`libtmux.Server`

    Other Parameters
    ----------------
    args : list
        Arguments passed into :meth:`Server.new_session`
    kwargs : dict
        Keyword arguments passed into :meth:`Server.new_session`

    Yields
    ------
    :class:`libtmux.Session`
        Temporary session

    Examples
    --------

    >>> with temp_session(server) as session:
    ...     session.new_window(window_name='my window')
    """

    if "session_name" in kwargs:
        session_name = kwargs.pop("session_name")
    else:
        session_name = get_test_session_name(server)

    session = server.new_session(session_name, *args, **kwargs)

    try:
        yield session
    finally:
        if server.has_session(session_name):
            session.kill_session()
    return


@contextlib.contextmanager
def temp_window(session, *args, **kwargs):
    """
    Return a context manager with a temporary window.

    The window will destroy itself upon closing with :meth:`window.
    kill_window()`.

    If no ``window_name`` is entered, :func:`get_test_window_name` will make
    an unused window name.

    Parameters
    ----------
    session : :class:`libtmux.Session`

    Other Parameters
    ----------------
    args : list
        Arguments passed into :meth:`Session.new_window`
    kwargs : dict
        Keyword arguments passed into :meth:`Session.new_window`

    Yields
    ------
    :class:`libtmux.Window`
        temporary window

    Examples
    --------

    >>> with temp_window(session) as window:
    ...     my_pane = window.split_window()
    """

    if "window_name" not in kwargs:
        window_name = get_test_window_name(session)
    else:
        window_name = kwargs.pop("window_name")

    window = session.new_window(window_name, *args, **kwargs)

    # Get ``window_id`` before returning it, it may be killed within context.
    window_id = window.get("window_id")

    try:
        yield session
    finally:
        if session.findWhere(window_id=window_id):
            window.kill_window()
    return


class EnvironmentVarGuard:

    """Mock environmental variables safetly.

    Helps rotect the environment variable properly.  Can be used as context
    manager.

    Notes
    -----

    Vendorized to fix issue with Anaconda Python 2 not including test module,
    see #121 [1]_

    References
    ----------

    .. [1] Just installed, "ImportError: cannot import name test_support".
       GitHub issue for tmuxp. https://github.com/tmux-python/tmuxp/issues/121.
       Created October 12th, 2015. Accessed April 7th, 2018.
    """

    def __init__(self):
        self._environ = os.environ
        self._unset = set()
        self._reset = dict()

    def set(self, envvar, value):
        if envvar not in self._environ:
            self._unset.add(envvar)
        else:
            self._reset[envvar] = self._environ[envvar]
        self._environ[envvar] = value

    def unset(self, envvar):
        if envvar in self._environ:
            self._reset[envvar] = self._environ[envvar]
            del self._environ[envvar]

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        for envvar, value in self._reset.items():
            self._environ[envvar] = value
        for unset in self._unset:
            del self._environ[unset]
