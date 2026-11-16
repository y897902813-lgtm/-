#!/usr/bin/env python3
"""MuJoCo Lab v1.0 UDP collector/packet monitor for development.

Standard library only; no Studio Server or MATLAB installation required.
Handles plain JSON and interleaved/out-of-order ML1 fragments with SHA checks.
Run on the target host (Simulink side):
    python scripts/mujoco_lab_udp_receiver.py --host 127.0.0.1 --port 9090
This is a diagnostic receiver, NOT a Simulink block or delivery guarantee.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_MESSAGE_BYTES = 1024 * 1024
MAX_PARTS = 1024
MAX_IN_FLIGHT = 128
STALE_AFTER_S = 8.0


@dataclass
class _InFlight:
    total: int
    digest: str
    first_seen: float
    chunks: dict[int, bytes] = field(default_factory=dict)
    size: int = 0


class LabDatagramCollector:
    """Input datagrams and get a complete validated decoded JSON dict or None."""

    def __init__(self) -> None:
        self.pending: dict[tuple[str, int, str], _InFlight] = {}
        self.completed = 0
        self.bad_packets = 0
        self.dropped_incomplete = 0

    def _expire(self, now: float) -> None:
        for key, slot in list(self.pending.items()):
            if now - slot.first_seen > STALE_AFTER_S:
                self.pending.pop(key, None)
                self.dropped_incomplete += 1
        if len(self.pending) > MAX_IN_FLIGHT:
            for key in sorted(self.pending, key=lambda key: self.pending[key].first_seen)[:len(self.pending)-MAX_IN_FLIGHT]:
                self.pending.pop(key, None)
                self.dropped_incomplete += 1

    def feed(self, packet: bytes, sender: tuple[str, int], *, now: float | None = None) -> dict[str, Any] | None:
        clock = time.monotonic() if now is None else now
        self._expire(clock)
        try:
            if len(packet) > 65507:
                raise ValueError('oversized UDP packet')
            envelope = json.loads(packet.decode('utf-8'))
            if not isinstance(envelope, dict):
                raise ValueError('payload is not a JSON object')
            if envelope.get('p') != 'ML1':
                if envelope.get('type') not in {'state', 'timeline'}:
                    raise ValueError('missing JSON protocol type')
                self.completed += 1
                return envelope
            mid, total, index, digest = envelope['id'], envelope['total'], envelope['index'], envelope['sha']
            if not isinstance(mid, str) or not 1 <= len(mid) <= 64 or not isinstance(digest, str) or len(digest) != 16:
                raise ValueError('invalid ML1 fragment metadata')
            if type(total) is not int or type(index) is not int or not 1 <= total <= MAX_PARTS or not 0 <= index < total:
                raise ValueError('invalid ML1 indexes')
            fragment = base64.b64decode(envelope['data'], validate=True)
            if not fragment or len(fragment) > 65507:
                raise ValueError('invalid fragment size')
            key=(sender[0],int(sender[1]),mid)
            slot=self.pending.get(key)
            if slot is None:
                slot=_InFlight(total,digest,clock)
                self.pending[key]=slot
            elif slot.total!=total or slot.digest!=digest:
                self.pending.pop(key,None)
                raise ValueError('fragment metadata conflict')
            previous=slot.chunks.get(index)
            if previous is not None:
                if previous != fragment:
                    self.pending.pop(key,None)
                    raise ValueError('fragment duplicate differs')
                return None
            slot.chunks[index]=fragment
            slot.size+=len(fragment)
            if slot.size > MAX_MESSAGE_BYTES:
                self.pending.pop(key,None)
                raise ValueError('message too large')
            if len(slot.chunks)!=total:
                self._expire(clock)
                return None
            self.pending.pop(key,None)
            raw=b''.join(slot.chunks[i] for i in range(total))
            if hashlib.sha256(raw).hexdigest()[:16]!=digest:
                raise ValueError('ML1 message SHA256 checksum mismatch')
            message=json.loads(raw.decode('utf-8'))
            if not isinstance(message,dict) or message.get('type') not in {'state','timeline'}:
                raise ValueError('reassembled JSON protocol invalid')
            self.completed+=1
            return message
        except (ValueError, UnicodeError, KeyError, TypeError, OverflowError) as exc:
            self.bad_packets+=1
            raise ValueError(f'UDP parse/reassembly rejected packet: {exc}') from exc


def main() -> None:
    parser=argparse.ArgumentParser(description='MuJoCo Lab UDP JSON reassembly and live packet monitor')
    parser.add_argument('--host',default='127.0.0.1',help='local bind address (0.0.0.0 for external receivers)')
    parser.add_argument('--port',type=int,default=9090,help='local listening port, default 9090')
    parser.add_argument('--once',action='store_true',help='exit after first complete JSON message')
    parser.add_argument('--output',type=Path,help='optional append-only JSONL capture file')
    args=parser.parse_args()
    collector=LabDatagramCollector()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.bind((args.host,args.port))
        udp.settimeout(1.0)
        print(f'Listening on {args.host}:{args.port} (plain JSON + ML1 fragments); Ctrl+C exits',flush=True)
        try:
            while True:
                try:
                    packet,sender=udp.recvfrom(65535)
                except socket.timeout:
                    collector._expire(time.monotonic())
                    continue
                try:
                    msg=collector.feed(packet,sender)
                except ValueError as exc:
                    print(f'DROP from {sender[0]}:{sender[1]}: {exc}',flush=True)
                    continue
                if msg is None:continue
                rendered=json.dumps(msg,ensure_ascii=False,indent=2,allow_nan=False)
                print(f'\n{sender[0]}:{sender[1]} type={msg["type"]} '
                      f'object={msg.get("object_id")} seq={msg.get("sequence_id")} '
                      f'run={msg.get("run_id")} sim_time_s={msg.get("sim_time_s", "plan")}\n{rendered}',flush=True)
                if args.output:
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    with args.output.open('a',encoding='utf-8') as f:
                        f.write(json.dumps(msg,ensure_ascii=False,allow_nan=False)+'\n')
                if args.once:break
        except KeyboardInterrupt:
            pass
    print(f'complete={collector.completed}, bad={collector.bad_packets}, expired={collector.dropped_incomplete}',flush=True)


if __name__=='__main__':main()
