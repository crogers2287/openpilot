#!/usr/bin/env python3

import time
from multiprocessing import Process

from openpilot.common.params import Params
from openpilot.system.manager.process import launcher
from openpilot.common.swaglog import cloudlog
from openpilot.system.hardware import HARDWARE
from openpilot.system.version import get_build_metadata

ATHENA_MGR_PID_PARAM = "AthenadPid"


def main():
  manage_athenad("DongleId", ATHENA_MGR_PID_PARAM, 'athenad', 'system.athena.athenad')


def manage_athenad(dongle_id_param, pid_param, process_name, target):
  params = Params()
  dongle_id = params.get(dongle_id_param)
  build_metadata = get_build_metadata()

  cloudlog.bind_global(dongle_id=dongle_id,
                       version=build_metadata.openpilot.version,
                       origin=build_metadata.openpilot.git_normalized_origin,
                       branch=build_metadata.channel,
                       commit=build_metadata.openpilot.git_commit,
                       dirty=build_metadata.openpilot.is_dirty,
                       device=HARDWARE.get_device_type())

  def _bd_dm_relaxed():
    # BlueDragon: True when DM is Passive/Off (BPDmMode != 0) -> keep athena offline
    v = params.get("BPDmMode")
    if isinstance(v, bytes):
      v = v.decode()
    return (v or "0").strip() not in ("", "0")

  try:
    while 1:
      # BlueDragon: don't connect to comma while DM is Passive/Off
      if _bd_dm_relaxed():
        time.sleep(5)
        continue
      cloudlog.info(f"starting {process_name} daemon")
      proc = Process(name=process_name, target=launcher, args=(target, process_name))
      proc.start()
      # stop the comma connection if DM is switched to Passive/Off while running
      while proc.is_alive():
        if _bd_dm_relaxed():
          cloudlog.info(f"BlueDragon: DM relaxed, stopping {process_name}")
          proc.terminate()
          break
        proc.join(timeout=2)
      proc.join()
      cloudlog.event(f"{process_name} exited", exitcode=proc.exitcode)
      time.sleep(5)
  except Exception:
    cloudlog.exception(f"manage_{process_name}.exception")
  finally:
    params.remove(pid_param)

if __name__ == '__main__':
  main()
