#!/bin/sh
# Install numpy + OpenCV (the `vision` extra) into the pick PC's current venv from wheels
# already copied to its /tmp — the PC has no internet on the cell. Run from the Air:
#   scripts/pi-vision-install.sh nick@192.168.3.20
set -e
target="${1:?usage: pi-vision-install.sh user@pickpc}"
ssh "$target" 'sudo /opt/perceptronics/current/bin/pip install --no-index /tmp/numpy-*.whl /tmp/opencv_python_headless-*.whl >/dev/null && /opt/perceptronics/current/bin/python -c "import numpy, cv2; print(\"vision ok:\", numpy.__version__, cv2.__version__)"'
