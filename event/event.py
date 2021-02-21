import subprocess
import datetime
import os
from generic import get_now, gen_hier, create_logger, indent
import shlex
import yaml
import logging
import tempfile
import time


logger = create_logger("Event")


class CallBack:

    logger = logger

    def __init__(self, name, cmd, env=None, working_directory=None):
        self.name = name
        self._cmd = shlex.split(cmd)
        self.start_time = None
        self.end_time = None
        self.worker = None
        self.env = env
        self.wd = working_directory
        self._is_done = True
        self.stdout_tmpfile = None
        self.stderr_tmpfile = None
        self.timeout = 10
        # self.basename = os.path.basename(name).replace(" ", "_")

    def get_cmd(self):
        return " ".join(self._cmd)

    def _run_cmd(self):
        self._is_done = False
        self.start_time = get_now()

        try:
            self.stdout_tmpfile = tempfile.NamedTemporaryFile(
                # prefix="{name}_stdout_".format(self.basename),
                prefix="stdout_",
                delete=False,
                suffix=".log",
            )
            self.stderr_tmpfile = tempfile.NamedTemporaryFile(
                # prefix="{name}_stderr_".format(self.basename),
                prefix="stderr_",
                delete=False,
                suffix=".log",
            )

            self.worker = subprocess.Popen(
                self._cmd,
                env=self.env,
                cwd=self.wd,
                stdout=self.stdout_tmpfile,
                stderr=self.stderr_tmpfile,
            )

        except:
            self.logger.exception('failed to execute command "%s"', self.get_cmd())
            raise

    def _poll(self):
        if self.worker is None:
            return 0

        self.worker.poll()

        # self.logger.debug("%s %s %s", self.name, self.worker.pid, self.worker.returncode)

        if self.worker.returncode is not None:
            self.end_time = get_now()
            self._is_done = True
            self.close_tmpfile()

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    '"{name}" exited with {code}'.format(
                        name=self.name,
                        code=self.worker.returncode,
                    )
                )

        return self.worker.returncode

    @property
    def returncode(self):
        if self.worker is None:
            return 0
        return self.worker.returncode

    @property
    def is_done(self):
        return self._is_done or self._poll() != None

    @property
    def stderr(self):
        with open(self.stderr_tmpfile.name, "r") as stderr:
            stderr.seek(0)
            for line in stderr.readlines():
                yield line.rstrip("\n")

    @property
    def stdout(self):
        with open(self.stdout_tmpfile.name, "r") as stdout:
            stdout.seek(0)
            for line in stdout.readlines():
                yield line.rstrip("\n")

    def __call__(self):
        self._run_cmd()

    def kill(self):
        try:
            if self._poll() == None:
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
            out=self.stdout_tmpfile.name,
            err=self.stderr_tmpfile.name,
        ).copy()

    def communicate(self):
        self._run_cmd()
        timeout_cnt = 0
        while self._poll() == None:
            timeout_cnt += 1
            if timeout_cnt > self.timeout:
                self.kill()
                self.logger.error(
                    '"%s" failed due to %ss timeout\n%s',
                    self.name,
                    self.timeout,
                    self.dump_err(),
                )
                return None, None
            time.sleep(1)

        return self.stdout_tmpfile.name, self.stderr_tmpfile.name

    def dump_err(self):
        return "\n".join(self.iter_err())

    def iter_err(self):
        # if not self._is_done:
        #     return None
        # yield msg.format("Command", " ".join(self.cmd), indent=indent)
        yield indent + "CMD:"
        yield 2 * indent + self.get_cmd()

        # if self.logger.isEnabledFor(logging.DEBUG):
        #     yield indent + "OUT:"
        #     for line in self.stdout:
        #         yield 2*indent + line.rstrip("\n")

        if self.returncode != 0:
            yield indent + "ERR:"
            for line in self.stderr:
                yield 2 * indent + line

    def iter_out(self):
        yield indent + "OUT:"
        for line in self.stdout:
            yield 2 * indent + line

    def dump_out(self):
        return "\n".join(self.iter_out())

    def close_tmpfile(self):
        try:
            if self.stderr_tmpfile:
                self.stderr_tmpfile.close()
            if self.stdout_tmpfile:
                self.stdout_tmpfile.close()
        except:
            self.logger.exception("failed to close tempfile")


class CallBackPool:

    logger = logger

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

            if self.current_job.returncode != 0:
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

    logger = logger

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
            callback_pool.add(name, cmd, **kwargs)

        self.events[event_name] = callback_pool

    def on(self, event):
        if event not in self.events:
            event = "any"

        callbackpool = self.events.get(event, None)

        if callbackpool is not None:
            callbackpool.run()

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
            '"{0}" failed\n{info}'.format(job_info.name, info=job_info.dump_err())
        )
        if self.error_handler is not None:
            self.error_handler.env.update({"__EVENT_NAME__": job_info.name})
            self.error_handler.communicate()
            if self.logger.isEnabledFor(logging.DEBUG):
                if self.error_handler.returncode != 0:
                    msg = self.error_handler.dump_err()
                else:
                    msg = ""
                msg += self.error_handler.dump_out()
                self.logger.debug("ErrorHandler:\n%s", msg)

    def on_success(self):
        if self.success_handler is not None:
            self.success_handler.communicate()
            if self.logger.isEnabledFor(logging.DEBUG):
                if self.success_handler.returncode != 0:
                    msg = self.success_handler.dump_err()
                else:
                    msg = ""
                msg += self.success_handler.dump_out()
                self.logger.debug("SuccessHandler:\n%s", msg)
