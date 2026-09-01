#!/usr/bin/env bash
set -euo pipefail

worldgen generate   "雨上がりの未来的な神社。濡れた石畳、伝統木造と淡い発光ガラスの融合。人物はいない。"   --name cyber-shrine   --output outputs/cyber-shrine   --duration 10   --camera-path arc-clockwise   --orbit-degrees 45   --dry-run
