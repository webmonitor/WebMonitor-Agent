#!/bin/bash
set -euo pipefail
exec squid -N -f /etc/squid/squid.conf
