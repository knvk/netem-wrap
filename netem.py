#!/usr/bin/python3

import yaml
import time
import argparse
import os
from datetime import datetime
from math import inf
import signal


def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fd:
            config = yaml.safe_load(fd)
    except FileNotFoundError as e:
        print(e)
        os._exit(2)

    return config


def run(config: dict):

    print("Adding tc-prio")
    os.system(f"sudo tc qdisc add dev {
              config['interface']} root handle 1: prio priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0")
    print("Adding filters")
    # make sure we start clean
    os.system(f"sudo tc filter del dev {config['interface']}")
    # split qdist to 2 prio queues: 2nd for x.x.x.x/y 1st for 0.0.0.0/0
    os.system(f"sudo tc filter add dev {
              config['interface']} protocol ip parent 1: prio 1 u32 match ip dst {config['filter']} flowid 1:2")
    os.system(f"sudo tc filter add dev {
              config['interface']} protocol all parent 1: prio 2 u32 match ip dst 0.0.0.0/0 flowid 1:1")

    cleared = True
    for rule in config['events']:
        start = str(datetime.now())
        print(f"ts:\t{start}\tduration:\t{rule['duration']:10}ms\trules:\t{
              ' '.join(str(x) for x in rule['rules'])}")
        cleared = apply_rule(config['interface'], rule, cleared)

    print("Deleting filters")
    os.system(f"sudo tc filter del dev {config['interface']}")
    print("Deleting tc-prio")
    # OS will apply default one after deleting last 
    os.system(f"sudo tc qdisc del dev {config['interface']} root")


def apply_rule(interface: str, event: dict, clear: bool):
    if event['rules'][0] == 'clear':
        if not clear:
            cmd = f'sudo tc qdisc del dev {interface} parent 1:2'
            clear = True
        else:
            # do nothing
            cmd = ':'
            clear = True
    else:
        if not clear:
            print("Previous rule not cleared, deleting")
            os.system(f'sudo tc qdisc del dev {interface} parent 1:2')

        cmd = f'sudo tc qdisc add dev {interface} parent 1:2 handle 10: netem'
        for rule in event['rules']:
            cmd += ' ' + rule
        clear = False

    os.system(cmd)
    time.sleep(event['duration']/1000)

    return clear


def get_counts(config: dict):
    # run once if not specified
    count = config.get('repeat', 1)
    if count == 'forever':
        return inf
    return count


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Network loss simulation script. For rules check: https://man7.org/linux/man-pages/man8/tc-netem.8.html')

    parser.add_argument('--config', '-c', default='example.yaml',
                        help='Config file for the simulation rules.')

    args = parser.parse_args()

    config = load_config(args.config)

    def sig_int_handler(signum, frame):
        print(f'Got SIG {signum}')
        os.system(f"sudo tc filter del dev {config['interface']}")
        os.system(f"sudo tc qdisc del dev {config['interface']} root")
        os._exit(1)

    signal.signal(signal.SIGINT, sig_int_handler)

    count = get_counts(config)
    i = 0
    while (count - i) > 0:
        print(f'Running {i + 1} of {count}')
        run(config)
        i += 1
