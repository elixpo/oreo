"""Shared helpers: run the CLI against a FakeTransport and capture output."""

import io

from fake import FakeTransport, ScriptedInput, badge_port  # noqa: F401

from oreo_cli.main import main
from oreo_cli.ui import UI


class Run:
    def __init__(self, rc, out, links, fake, ui):
        self.rc = rc
        self.out = out
        self.links = links
        self.fake = fake
        self.ui = ui


def run_cli(argv, fake=None, ports=None, inputs=(), secret=None, interactive=False,
            runner=None):
    buf = io.StringIO()
    secret_calls = []

    def default_secret(prompt):
        secret_calls.append(prompt)
        raise AssertionError("unexpected password prompt")
    ui = UI(file=buf, color=False, width=200, input_fn=ScriptedInput(*inputs),
            secret_fn=secret or default_secret, interactive=interactive)
    links = []

    def factory(port):
        links.append(port)
        if fake is None:
            raise AssertionError("the badge was touched")
        return fake
    rc = main(argv, ui=ui,
              comports=(lambda: list(ports)) if ports is not None else (lambda: [badge_port()]),
              link_factory=factory, runner=runner)
    return Run(rc, buf.getvalue(), links, fake, ui)
