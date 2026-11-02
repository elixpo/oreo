Flash the complete OreoOS image with `./deploy --full` from the OreoOS
repository, which writes this firmware and the Doom game data and installs the
OS files. To write only the firmware:

```bash
python -m esptool --chip esp32s3 --port /dev/ttyACM0 erase-flash
python -m esptool --chip esp32s3 --port /dev/ttyACM0 write-flash 0 firmware.bin
```

The Doom game data goes into the `doom` partition (see
`partitions-oreo-badge.csv`):

```bash
python tools/fetch_freedoom.py
python -m esptool --chip esp32s3 --port /dev/ttyACM0 write-flash 0x250000 oreoWare/doom/freedoom1.owz
```
