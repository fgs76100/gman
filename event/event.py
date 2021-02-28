import subprocess
import datetime
import os
import shlex
import logging
import tempfile
import time
import yaml
import threading
from generic import get_now, gen_hier, create_logger, indent


LOGGER = create_logger("Event")

EXECUTE_FAIL = 191
SUCCESS = 0

ANY_EVENT = "any"  # speical event will trigger if none of events match


class PopenThread(threading.Thread):
    """
    create a thead has same API as subprocess.Popen
    """

    def __init__(self, **kwargs):
        super(PopenThread, self).__init__(
            group=kwargs.get("group", None),
            target=kwargs.get("target", None),
            name=kwargs.get("name", None),
            args=kwargs.get("args", []),
            kwargs=kwargs.get("kwargs", {}),
        )
        self.daemon = True
        self.pid = 0

    def poll(self):
        return self.returncode

    def kill(self):
        pass

    @property
    def returncode(self):
        if self.is_alive():
            return None

        return SUCCESS


class CallBack:

    logger = LOGGER

    def __init__(self, name, cmd, env=None, **kwargs):
        self.name = name
        self.worker = None
        self._is_done = True
        self.stdout_tmpfile = None
        self.timeout = 10
        self.history = dict()
        self.env = env or {}
        self.kwargs = kwargs
        self.returncode = SUCCESS

        if callable(cmd):
            # cmd is python function
            self._cmd = cmd
        else:
            # cmd is a command line string
            self._cmd = shlex.split(cmd)

    def get_cmd(self):
        if callable(self._cmd):
            return self._cmd.__name__

        return " ".join(self._cmd)

    def _run_func(self):
        # if self._cmd is python functio
        self.worker = PopenThread(target=self._cmd, **self.kwargs)
        self.worker.start()

    def _run_os_cmd(self):
        # if self._cmd is os command line

        self.start_time = get_now()
        basename = os.path.basename(self.name).replace(" ", "_")

        self.stdout_tmpfile = tempfile.NamedTemporaryFile(
            prefix="%s_stdout_" % basename,
            delete=False,
            suffix=".log",
        )
        # self.stderr_tmpfile = tempfile.NamedTemporaryFile(
        #     # prefix="{name}_stderr_".format(self.basename),
        #     prefix="event_stderr_",
        #     delete=False,
        #     suffix=".log",
        # )

        self.worker = subprocess.Popen(
            self._cmd,
            env=self.env,
            stdout=self.stdout_tmpfile,
            # stderr=self.stderr_tmpfile,
            stderr=subprocess.STDOUT,
            **self.kwargs
        )
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("%s\n%s", "%s was invoked" % self.name, self.get_info())

    def get_info(self, _indent=indent):
        if callable(self._cmd):
            info = ["%sFunc: %s" % (_indent, self.get_cmd())]
        else:
            info = [
                "%sCMD: %s" % (_indent, self.get_cmd()),
                "%sLOG: %s" % (_indent, self.stdout_tmpfile.name),
            ]
        return "\n".join(info)

    def _poll(self):
        if self._is_done or not self.worker:
            return self.returncode

        if self.worker:
            self.worker.poll()
            self.returncode = self.worker.returncode

        if self.returncode is not None:
            self.end_time = get_now()
            self._is_done = True
            self.close_tmpfile()

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "{name} exited with {code}\n{info}".format(
                        name=self.name,
                        code=self.returncode,
                        info=self.get_info(),
                    )
                )

        return self.returncode

    @property
    def is_done(self):
        return self._is_done or self._poll() != None

    def __call__(self):
        self._is_done = False
        self.returncode = None
        try:
            if callable(self._cmd):
                self._run_func()
            else:
                self._run_os_cmd()
        except:
            self.logger.exception('failed to execute command "%s"', self.get_cmd())
            self.returncode = EXECUTE_FAIL
            raise

    def kill(self):
        try:
            if self.worker and self._poll() == None:
                self.worker.kill()
        except OSError:
            pass
        except:
            self.logger.exception("failed to kill process: PID = %s", self.worker.pid)
        finally:
            self.close_tmpfile()

    def get_history(self):
        if not self._is_done:
            return None

        return dict(
            name=self.name,
            cmd=self.get_cmd(),
            start_time=self.start_time,
            end_time=self.end_time,
            returncode=self.returncode,
            log=self.stdout_tmpfile.name if self.stdout_tmpfile else "not available",
            # err=self.stderr_tmpfile.name,
        ).copy()

    def communicate(self):
        self.__call__()
        timeout_cnt = 0
        while self._poll() == None:
            timeout_cnt += 1
            if timeout_cnt > self.timeout:
                self.kill()
                self.logger.error(
                    '"%s" failed due to %ss timeout\n',
                    self.name,
                    self.timeout,
                    # self.dump_err(),
                )
                return None, None
            time.sleep(1)

        # return self.stdout_tmpfile.name, self.stderr_tmpfile.name
        if self.stdout_tmpfile:
            return self.stdout_tmpfile.name
        else:
            return None

    def close_tmpfile(self):
        try:
            # if self.stderr_tmpfile:
            #     self.stderr_tmpfile.close()
            if self.stdout_tmpfile:
                self.stdout_tmpfile.close()
        except:
            self.logger.exception("failed to close tempfile")


class CallBackPool:

    logger = LOGGER

    def __init__(self, name, continue_on_error=False):
        self.continue_on_error = continue_on_error
        self.name = name
        self.pool = []
        self.pool_index = 0
        self.current_job = None
        self.histories = []
        self._is_done = True
        self._bind = {}

    def add(self, name, cmd, **kwargs):
        self.pool.append(CallBack(gen_hier(self.name, name), cmd, **kwargs))

    def _run_job(self):
        self.current_job = self.pool[self.pool_index]
        self.current_job()
        self.pool_index += 1

        if self.pool_index >= len(self.pool):
            self.pool_index = 0

    def run(self):
        self._is_done = False
        self.pool_index = 0
        self._run_job()

    @property
    def is_done(self):
        return self._is_done or self._poll()

    def _poll(self):
        if self.current_job.is_done:

            if self.current_job.returncode != SUCCESS:
                self.emit("error", self.current_job)
                if not self.continue_on_error:
                    self._is_done = True

            elif self.pool_index == 0:
                self._is_done = True
                self.emit("success")

            if not self._is_done:
                self._run_job()

        return self._is_done

    def emit(self, signal, *args, **kwargs):
        if signal in self._bind:
            callback = self._bind[signal]
            callback(*args, **kwargs)

    def bind(self, signal, callback):
        self._bind[signal] = callback

    def kill(self):
        for job in self.pool:
            job.kill()


class EventManger:

    logger = LOGGER

    def __init__(self, name="", env=None):
        self.name = name
        self.env = env
        self.events = {}
        self.error_handler = None
        self.success_handler = None

    def kill(self):
        for pool in self.events.values():
            pool.kill()

    def add_event(self, event_name, callbacks, continue_on_error=False, **kwargs):

        callback_pool = CallBackPool(gen_hier(self.name, event_name), continue_on_error)

        for callback in callbacks:
            name = callback.get("name", "")
            cmd = callback.get("cmd")
            # kwargs.update(callback)
            callback.update(kwargs)
            callback_pool.add(**callback)

        self.events[event_name] = callback_pool

    def on(self, event):
        if event not in self.events:
            event = ANY_EVENT

        callbackpool = self.events.get(event, None)

        if callbackpool is not None:
            callbackpool.run()

    # def add_handler(self, signal, name, cmd, **kwargs):
    #     name = gen_hier(signal, name)

    def add_error_handler(self, name, cmd, **kwargs):
        name = gen_hier("on_error", name)
        self.error_handler = CallBack(gen_hier(self.name, name), cmd, **kwargs)
        for job in self.events.values():
            job.bind("error", self.on_error)

    def add_success_handler(self, name, cmd, **kwargs):
        name = gen_hier("on_success", name)
        self.success_handler = CallBack(gen_hier(self.name, name), cmd, **kwargs)
        for job in self.events.values():
            job.bind("success", self.on_success)

    @property
    def is_done(self):
        return all([pool.is_done for pool in self.events.values()])

    def on_error(self, job_info):
        self.logger.error(
            '"{0}" failed\n{info}'.format(job_info.name, info=job_info.get_info())
        )
        try:
            if self.error_handler is not None:
                self.error_handler.env.update({"__EVENT_NAME__": job_info.name})
                self.error_handler.communicate()
                # if self.logger.isEnabledFor(logging.DEBUG):
                if self.error_handler.returncode != SUCCESS:
                    msg = self.error_handler.get_info()
                    self.logger.debug("ErrorHandler:\n%s", msg)
        except:
            self.logger.exception(
                "failed to run 'on_error'\n%s", self.error_handler.get_info()
            )

    def on_success(self):
        try:
            if self.success_handler is not None:
                self.success_handler.communicate()
                # if self.logger.isEnabledFor(logging.DEBUG):
                if self.success_handler.returncode != SUCCESS:
                    msg = self.success_handler.get_info()
                    self.logger.debug("SuccessHandler:\n%s", msg)
        except:
            self.logger.exception(
                "failed to run 'on_success'\n%s", self.success_handler.get_info()
            )
