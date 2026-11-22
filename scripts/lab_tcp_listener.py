"""Temporary TCP listeners for the AI-SOC Ubuntu lab."""

import argparse
import selectors
import socket
import sys
import time
from contextlib import ExitStack


BIND_IP = '10.0.2.15'
PORTS = tuple(range(18080, 18088))
MAX_SECONDS = 300


def run(check_only):
    deadline = time.monotonic() + MAX_SECONDS
    with ExitStack() as stack:
        sockets = []
        for port in PORTS:
            listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            try:
                listener.bind((BIND_IP, port))
            except OSError as error:
                raise RuntimeError(f'Could not bind {BIND_IP}:{port}: {error.strerror}') from error
            sockets.append(listener)

        if check_only:
            print(f'Ubuntu bind check passed for {BIND_IP}, TCP ports 18080–18087.', flush=True)
            return

        selector = stack.enter_context(selectors.DefaultSelector())
        for listener in sockets:
            listener.listen(8)
            listener.setblocking(False)
            selector.register(listener, selectors.EVENT_READ)

        print(f'Ready on {BIND_IP}, TCP ports 18080–18087. Ctrl+C to stop. Maximum runtime: five minutes.', flush=True)
        while (remaining := deadline - time.monotonic()) > 0:
            for key, _ in selector.select(timeout=remaining):
                if time.monotonic() >= deadline:
                    return
                try:
                    connection, _ = key.fileobj.accept()
                except BlockingIOError:
                    continue
                connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check bind availability and exit before listening.')
    args = parser.parse_args()
    try:
        run(args.check)
    except KeyboardInterrupt:
        print('\nStopped. Lab sockets closed.')
        return 130 if args.check else 0
    except (OSError, RuntimeError) as error:
        print(f'Setup failed. Lab sockets closed. {error}', file=sys.stderr)
        return 1
    if not args.check:
        print('Five-minute limit reached. Lab sockets closed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
