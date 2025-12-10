#!/usr/bin/env bash
set -e
service openvswitch-switch start
exec tail -f /dev/null