"""
A minimal web application for checking the status of a GC3Pie session.

Provides a REST API to perform the basic GC3Pie operations on jobs,
plus a status page reporting some basic metrics.

It is implemented as a `Flask <http://flask.pocoo.org/>` "blueprint"
for easier embedding into larger web applications.
"""
# Copyright (C) 2015 S3IT, University of Zurich.
#
# Authors:
#   Riccardo Murri <riccardo.murri@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import absolute_import

__docformat__ = 'reStructuredText'
__version__ = '$Revision$'


# stdlib imports
from collections import defaultdict
import functools
import itertools
import threading
import time

# local imports
import gc3libs
import gc3libs.core
import gc3libs.session


def _get_scheduler_and_lock_factory(lib):
    """
    Return factories for creating a period task scheduler and locks.

    The scheduler will be a scheduler class from the APScheduler_
    framework (which see for the API), and the lock factory is an
    appropriate locking object for synchronizing independently running
    tasks. Example::

        sched_factory, lock_factory = _get_scheduler_and_lock_factory('threading')
        sched = sched_factory()
        sched.add_job(task1, 'interval', seconds=5)
        sched.add_job(task2, 'interval', seconds=30)

        shared_data_lock = lock_factory()

        def task1():
          # ...
          with shared_data_lock:
            # modify shared data

    Argument `lib` is one of: ``threading``, ``gevent``, ``tornado``,
    ``asyncio`` (Python 3.5+ "async" system), ``twisted``, ``qt``;
    each of them selects a scheduler and lock objects compatible with
    the named framework for concurrent processing.

    .. _APScheduler: https://apscheduler.readthedocs.org/en/latest/userguide.html
    """
    if lib == 'threading':
        from apscheduler.schedulers.background import BackgroundScheduler
        from threading import Lock
        return (BackgroundScheduler, Lock)
    elif lib == 'gevent':
        from apscheduler.schedulers.gevent import GeventScheduler
        from gevent.lock import Semaphore
        return (GeventScheduler, Semaphore)
    elif lib in ['asyncio', 'tornado', 'twisted', 'qt']:
        raise NotImplemented(
            "Support for {lib} is not yet available!"
            .format(lib=lib))
    else:
        raise ValueError(
            "Library '{lib}' is unknown to `{mod}._get_scheduler_and_lock_factory()`"
            .format(lib=lib, mod=__name__))


def at_most_once_per_cycle(fn):
    """
    Ensure the decorated function is not executed more than once per
    each poll interval.

    Cached results are returned instead, if `Engine.progress()` has
    not been called in between two separate invocations of the wrapped
    function.
    """
    @functools.wraps(fn)
    def wrapper(self, *args):
        if not self._progress_last_run:
            return fn(self, *args)
        else:
            key = (fn, tuple(id(arg) for arg in args))
            try:
                update = (
                    self._cache_last_updated[key] < self._progress_last_run
                )
            except AttributeError:
                self._cache_last_updated = defaultdict(float)
                self._cache_value = dict()
                update = True
            if update:
                self._cache_value[key] = fn(self, *args)
                self._cache_last_updated[key] = time.time()
            return self._cache_value[key]
    return wrapper


class BgEngine(object):
    """
    Run a GC3Pie `Engine`:class: instance in the background.

    A `BgEngine` exposes the same interface as a regular `Engine`
    class, but proxies all operations for asynchronous execution by
    the wrapped `Engine` instance.  In practice, this means that all
    invocations of `Engine` operations on a `BgEngine` always succeed:
    errors will only be visible in the background thread of execution.
    """
    def __init__(self, lib, *args, **kwargs):
        """
        """
        sched_factory, lock_factory = _get_scheduler_and_lock_factory(lib)
        self._scheduler = sched_factory()

        # a queue for Engine ops
        self._q = []
        self._q_locked = lock_factory()

        assert len(args) > 0, (
            "`BgEngine()` must be called"
            " either with an `Engine` instance as first and only argument,"
            " or with a set of parameters to pass on to the `Engine` constructor.")
        if isinstance(args[0], gc3libs.core.Engine):
            # first (and only!) argument is an `Engine` instance, use that
            self._engine = args[0]
            assert len(args) == 1, (
                "If an `Engine` instance is passed to `BgEngine()`"
                " then it must be the only argument"
                " after the concurrency framework name.")
        else:
            # use supplied parameters to construct an `Engine`
            self._engine = gc3libs.core.Engine(*args, **kwargs)

        # no result caching until an update is really performed
        self._progress_last_run = 0


    #
    # control main loop scheduling
    #

    def start(self, interval):
        """
        Start triggering the main loop every `interval` seconds.
        """
        self.running = True
        self._scheduler.add_job((lambda: self._perform()),
                                'interval', seconds=interval)
        self._scheduler.start()
        gc3libs.log.info(
            "Started background execution of Engine %s every %d seconds",
            self._engine, interval)

    def stop(self, wait=False):
        """
        Stop background execution of the main loop.

        Call `start`:meth: to resume running.
        """
        gc3libs.log.info(
            "Stopping background execution of Engine %s ...", self._engine)
        self.running = False
        self._scheduler.shutdown(wait)

    def _perform(self):
        """
        Main loop: runs in a background thread after `start`:meth: has
        been called.

        There are two tasks that this loop performs:

        - Execute any queued engine commands.

        - Run `Engine.progress()` to ensure that GC3Pie tasks are updated.
        """
        gc3libs.log.debug("%s: _perform() started", self)
        # quickly grab a local copy of the command queue, and
        # reset it to the empty list -- we do not want to hold
        # the lock on the queue for a long time, as that would
        # make the API unresponsive
        with self._q_locked:
            q = self._q
            self._q = list()
        # execute delayed operations
        for fn, args, kwargs in q:
            gc3libs.log.debug(
                "Executing delayed call %s(*%r, **%r) ...",
                fn.__name__, args, kwargs)
            try:
                fn(*args, **kwargs)
            except Exception, err:
                gc3libs.log.error(
                    "Got %s executing delayed call %s(*%r, **%r): %s",
                    err.__class__.__name__,
                    fn.__name__, args, kwargs,
                    err, exc_info=__debug__)
        # update GC3Pie tasks
        gc3libs.log.debug(
            "%s: calling `progress()` on Engine %s ...",
            self, self._engine)
        try:
            self._engine.progress()
            self._progress_last_run = time.time()
        except Exception, err:
            gc3libs.log.error(
                "Got %s running `Engine.progress()` in the background: %s",
                err.__class__.__name__, err, exc_info=__debug__)
        gc3libs.log.debug("%s: _perform() done", self)

    #
    # Engine interface
    #

    def add(self, task):
        with self._q_locked:
            self._q.append((self._engine.add, (task,), {}))

    def close(self):
        with self._q_locked:
            self._q.append((self._engine.close, tuple(), {}))

    def fetch_output(self, task, output_dir=None,
                     overwrite=False, changed_only=True, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.fetch_output,
                            (task, output_dir, overwrite, changed_only),
                            extra_args))

    def free(self, task, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.free, (task,), extra_args))

    def get_resources(self):
        with self._q_locked:
            self._q.append((self._engine.get_resources, tuple(), {}))

    def get_backend(self, name):
        with self._q_locked:
            self._q.append((self._engine.get_backend, (name,), {}))

    def kill(self, task, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.kill, (task,), extra_args))

    def peek(self, task, what='stdout', offset=0, size=None, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.peek,
                           (task, what, offset, size), extra_args))

    def progress(self):
        """
        Proxy to `Engine.progress`.

        If the background thread is already running, this is a no-op,
        as progressing tasks is already taken care of by the
        background thread.  Otherwise, just forward the call to the
        wrapped engine.
        """
        if self.running:
            pass
        else:
            self._engine.progress()

    def remove(self, task):
        with self._q_locked:
            self._q.append((self._engine.remove, (task,), {}))

    def select_resource(self, match):
        with self._q_locked:
            self._q.append((self._engine.select_resource, (match,), {}))

    def stats(self, only=None):
        return self._engine.stats(only)

    def submit(self, task, resubmit=False, targets=None, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.submit, (task, resubmit, targets), extra_args))

    def update_job_state(self, *tasks, **extra_args):
        with self._q_locked:
            self._q.append((self._engine.update_job_state, tasks, extra_args))

    #
    # informational methods
    #

    def iter_tasks(self):
        """
        Iterate over all tasks managed by the Engine.
        """
        return itertools.chain(
            iter(self._engine._new),
            iter(self._engine._in_flight),
            iter(self._engine._stopped),
            iter(self._engine._terminating),
            iter(self._engine._terminated),
        )

    @at_most_once_per_cycle
    def stats_data(self):
        """
        Return global statistics about the jobs in the Engine.

        For each task state (and pseudo-state like ``ok`` or
        ``failed``), two values are returned: the count of managed
        tasks that were in that state when `Engine.progress()` was
        last run, and what percentage of the total managed tasks this
        is.

        This is basically an enriched version of `Engine.stats()`.
        """
        data = {}
        stats = self._engine.stats()
        tot = stats['total']
        for state, count in stats.items():
            data['count_' + state.lower()] = count
            data['percent_' + state.lower()] = 100.0 * count / max(tot, 1)
        return data

    @at_most_once_per_cycle
    def all_tasks_data(self):
        """
        Aggregate information from `task_data`:meth: into a single dictionary.

        Return a dictionary mapping task ID (a string) to the data
        returned by `task_data()` for that task.
        """
        data = {}
        for task in self.iter_tasks():
            task_data = self.task_data(task)
            task_id = task_data['id']
            data[task_id] = task_data
        return data

    @at_most_once_per_cycle
    def task_data(self, task, monitoring_depth=2):
        is_live = (
            gc3libs.Run.State.SUBMITTED,
            gc3libs.Run.State.RUNNING,
            gc3libs.Run.State.STOPPED
        )
        is_done = gc3libs.Run.State.TERMINATED
        failed = task.execution.exitcode != 0
        data = {
            'name':     task.jobname,
            'state':    task.execution.state,
            'is_live':  (task.execution.state in is_live),
            'is_done':  (task.execution.state in is_done),
            'failed':   (task.execution.state in is_done and failed),
            'percent_done': None,  # fix later, if possible
        }
        if hasattr(task, 'persistent_id'):
            data['id'] = str(task.persistent_id)
        # try to give percent completed
        # if (task.requested_walltime
        #         and (gc3libs.Run.State.RUNNING in task.execution.timestamp)):
        if gc3libs.Run.State.RUNNING in task.execution.timestamp:
            if isinstance(task, gc3libs.workflow.TaskCollection):
                # express completion as nr or finished jobs over total nr of jobs
                done = 0
                for child in task.tasks:
                    if (child.execution.state is gc3libs.Run.State.TERMINATED):
                        done += 1
                data['percent_done'] = done / len(task.tasks)
            elif isinstance(task, gc3libs.Task):
                # express completion as fraction of running time over requested walltime
                runtime = time.time() - task.execution.timestamp[gc3libs.Run.State.RUNNING]
                data['percent_done'] = 100.0 * runtime / task.requested_walltime.amount()
            else:
                raise NotImplementedError(
                    "Unhandled task class %r" % (task.__class__))
        return data

    @at_most_once_per_cycle
    def task_and_children_data(self, task):
        data = self.task_data(task)
        try:
            data['subtasks'] = list()
            for child in task.tasks:
                child_data = self.task_data(child)
                data['subtasks'].append(child_data)
            return data
        except AttributeError:
            # no `.tasks`
            return data
