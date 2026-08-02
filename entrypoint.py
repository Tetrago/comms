#!/usr/bin/env python3

import argparse
import datetime
import os
import re
import readline
import subprocess
import sys
import time

from ipaddress import IPv4Address
from pathlib import Path
from tabulate import tabulate
from typing import Dict, Any


class Color:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    NONE = "\033[0m"


class Logger:

    def __init__(self, path: Path):
        self.__file = open(path, "w")

    def print(self, *args, **kwargs):
        print(datetime.datetime.fromtimestamp(
            time.time()).strftime('%Y-%m-%d %H:%M:%S'),
              file=self.__file,
              end=": ",
              flush=False)
        print(*args, file=self.__file, flush=True, **kwargs)

    def close(self):
        self.__file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


LOGGER = Logger("/tmp/log")
CONFIG: Dict[str, Any] = {}
RULES: Dict[int, Dict[str, Any]] = {}

EFFECTS = {
    "broadcast": ("broadcast bitrate", "bps"),
    "duplicate": ("packet duplication rate", "[0,100]"),
    "jitter": ("variable latency effect (+/- jitter)", "s"),
    "latency": ("packet latency", "s"),
    "loss": ("packet loss rate", "[0,100]"),
    "unicast": ("broadcast (and multicast) bitrate", "bps"),
}

COMMANDS = [
    ("clear", "clears the screen", ["clear"]),
    ("del", "deletes an effect", ["d(el) <id> <effect>"]),
    ("exit", "terminates the container", ["exit"]),
    ("get", "displays effects for nodes", ["g(et) [id]"]),
    ("help", "displays this help menu", ["help", "?"]),
    ("set", "creates or modifies an effect",
     ["s(et) <id> <effect>=<value>", "s(et) ?"]),
    ("shell", "opens an interactive terminal (bash)", ["sh(ell)", "!"]),
]

OPTIONS = {
    "address": {
        "type": IPv4Address,
        "required": True,
        "help": "IPv4 address of virtual address"
    },
    ("H", "host-if"): {
        "type": str,
        "default": "lo",
        "help": "host EMANE channel multicast interface name"
    },
    "id": {
        "type":
        lambda x: int(x) if 0 < int(x) < 65535 else
        (_ for _ in
         ()).throw(argparse.ArgumentTypeError("must be in range [1, 65534]")),
        "required":
        False,
        "help":
        "id to use for node in EMANE network; otherwise derived from address"
    },
    "multicast": {
        "type": IPv4Address,
        "default": "224.1.2.8",
        "help": "multicast address for EMANE channel"
    },
    "virt-if": {
        "type": str,
        "default": "emane0",
        "help": "name of virtual interface to be created by EMANE"
    },
    "platform": {
        "type": Path,
        "default": "/data/platform.xml",
        "help": "location of platform config file"
    },
    "subnet": {
        "type": IPv4Address,
        "default": "255.255.255.0",
        "help": "subnet mask to use for virtual address"
    },
    ("I", "interfaces"): {
        "type":
        str,
        "required":
        False,
        "help":
        "comma separated list of additional interfaces to advertise EMANE links over"
    }
}


def configure_file(path: Path):
    with open(path, "r+") as f:
        data = f.read()

        for (name, value) in CONFIG.items():
            data = re.sub(rf"\{{\{{\s*{name}\s*\}}\}}", str(value), data)

        f.seek(0)
        f.write(data)
        f.truncate()


def apply_rules(id, rules):
    args = [
        str(x) for x in [
            "/usr/local/bin/emaneevent-commeffect", id, "-g",
            CONFIG["multicast"], "-i", CONFIG["host_if"], "-t", CONFIG["id"],
            "-r", id, "".join([f"{k}={v}" for k, v in rules.items()])
        ]
    ]

    LOGGER.print(*args)
    subprocess.run(args)


def update_rules_for(id: int):
    if id not in RULES:
        return

    if not RULES[id]:
        apply_rules(id, {"loss": 100})
    else:
        apply_rules(id, RULES[id])


def update_all_rules():
    for id in RULES.keys():
        update_rules_for(id)


def load_rules(options: Dict[str, str]):
    if not hasattr(load_rules, "re"):
        load_rules.re = re.compile(r"rule\.(?P<id>\d+)\.(?P<effect>[^.]+)")

    for key, value in options.items():
        if match := load_rules.re.fullmatch(key):
            id = int(match["id"])
            effect = match["effect"].lower()

            if id == CONFIG["id"]:
                print("Ignoring rule set on self: %s" % key, file=sys.stderr)
            elif effect not in EFFECTS.keys():
                print("Unknown effect: %s" % match["effect"], file=sys.stderr)
            else:
                set_rule(id, effect, value, update=False)


def set_rule(id: int, effect: str, value: str, update=True):
    if id == CONFIG["id"] or effect not in EFFECTS.keys():
        raise Exception(f"invalid ID or effect `{effect}`")

    RULES.setdefault(id, {})[effect] = value

    if update:
        update_rules_for(id)


def del_rule(id: int, effect: str, update=True) -> bool:
    if id == CONFIG["id"] or effect not in EFFECTS.keys():
        raise Exception(f"invalid ID or effect `{effect}`")

    if RULES.setdefault(id, {}).pop(effect, None) is None:
        return False

    if update:
        update_rules_for(id)

    return True


class EnvDefault(argparse.Action):

    def __init__(self, required=True, default=None, **kwargs):
        if value := os.environ.get(f"config.{kwargs['dest']}"):
            default = value

        if required and default:
            required = False

        super(EnvDefault, self).__init__(default=default,
                                         required=required,
                                         **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def parse_args() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(prog="emane")

    for (names, kwargs) in OPTIONS.items():
        if type(names) is str:
            names = (names[0], names)

        parser.add_argument(*("-" * (i + 1) + v for i, v in enumerate(names)),
                            action=EnvDefault,
                            **kwargs)

    return vars(parser.parse_args())


def resolve_id(addr: IPv4Address) -> int:
    if addr.packed[-2:] == [0, 0]:
        raise Exception("could not resolve ID from address")

    return addr.packed[2] * 256 + addr.packed[3]


def start_emane(platform: Path) -> subprocess.Popen:
    args = [
        "/usr/local/bin/emane", platform, "-l", "3", "-f", "/tmp/emane.log"
    ]

    LOGGER.print(*args)
    return subprocess.Popen(args, stderr=subprocess.DEVNULL)


def start_olsrd(interfaces: [str]) -> subprocess.Popen:
    args = [
        "/usr/local/sbin/olsrd", "-f", "/dev/null", "-nofork", "-i",
        *interfaces
    ]

    LOGGER.print(*args)
    return subprocess.Popen(args,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def wait_for_interfaces(interfaces: [str]):
    while not all([(Path("/sys/class/net") / x).exists() for x in interfaces]):
        time.sleep(0)


def print_rules_for(id: int):
    if id not in RULES.keys():
        print(f"{Color.YELLOW}No rules set{Color.NONE}")
    else:
        items = [[k, v] for k, v in RULES.setdefault(id, {}).items()]
        sorted(items, key=lambda x: x[0])
        print(tabulate(items, colalign=["left", "left"], tablefmt="pretty"))


def print_command_help():
    print(
        tabulate(
            ((f"{Color.BLUE}{cmd}{Color.NONE}", desc, "\n".join(
                [f"{Color.YELLOW}{x}{Color.NONE}" for x in usages]))
             for cmd, desc, usages in sorted(COMMANDS, key=lambda x: x[0])),
            headers=["Command", "Description", "Usage(s)"],
            colalign=["left"] * 3,
            tablefmt="pretty"))


def run_command(line):
    if not hasattr(run_command, "set"):
        run_command.set = re.compile(
            r"s(?:et)?\s+(?:(?P<id>\d+)\s+(?P<effect>\w+)\s*=\s*(?P<value>.*)|(?P<help>\?.*))"
        )
        run_command.rm = re.compile(r"d(?:el)?\s+(?P<id>\d+)\s+(?P<effect>.*)")
        run_command.get = re.compile(r"g(?:et)?(?:\s+(?P<id>\d+))?")

    if line == "clear":
        os.system("clear")
    elif line == "exit":
        raise EOFError
    elif line in ["!", "sh", "shell"]:
        subprocess.run(["/bin/bash"])
    elif line in ["?", "help"]:
        print_command_help()
    elif match := run_command.set.fullmatch(line):
        if match["help"]:
            print(
                tabulate(([k, *v] for k, v in EFFECTS.items()),
                         colalign=["left"] * 3,
                         tablefmt="pretty"))
        else:
            set_rule(int(match["id"]), match["effect"], match["value"])
    elif match := run_command.rm.fullmatch(line):
        if not del_rule(int(match["id"]), match["effect"]):
            print(f"{Color.YELLOW}No rule to delete{Color.NONE}")
        else:
            print(f"{Color.GREEN}Rule deleted{Color.NONE}")
    elif match := run_command.get.fullmatch(line):
        if match["id"]:
            print_rules_for(int(match["id"]))
        elif not any(RULES.values()):
            print(f"{Color.YELLOW}No rules set{Color.NONE}")
        else:
            for id in RULES.keys():
                if RULES[id]:
                    print(f"ID {id}:")
                    print_rules_for(id)
                    print()
    else:
        raise Exception("unrecognized command")


def shell():
    readline.set_history_length(64)
    readline.parse_and_bind(r'"\C-l": clear-screen')

    while True:
        try:
            line = input(
                f"[{Color.GREEN}%s{Color.NONE}]{Color.BLUE}~>{Color.NONE} " %
                CONFIG["address"])

            if line := line.strip():
                run_command(line)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except Exception as e:
            print(f"{Color.RED}{e}{Color.NONE}")


def main():
    global CONFIG

    CONFIG = parse_args()

    if not CONFIG["id"]:
        CONFIG["id"] = resolve_id(CONFIG["address"])

    configure_file(CONFIG["platform"])
    load_rules(os.environ)

    emane = start_emane(CONFIG["platform"])

    interfaces = [CONFIG["virt_if"]] + (CONFIG["interfaces"].split(",")
                                        if CONFIG["interfaces"] else [])
    wait_for_interfaces(interfaces)
    olsrd = start_olsrd(interfaces)

    # Hacky way to force EMANE to drop all links with no rules.
    apply_rules(65535, {"loss": 100})

    update_all_rules()
    shell()

    emane.terminate()
    olsrd.terminate()


if __name__ == "__main__":
    main()
