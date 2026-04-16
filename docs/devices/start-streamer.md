# USB Microscope Streamer

## Start

Run this on the hardware host that has the microscope attached:

```bash
sudo mjpg_streamer \
  -i "input_uvc.so -d ${AUTOPROBER_MICROSCOPE_DEV:-/dev/video0} -r 1600x1200 -f 15" \
  -o "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www"
```

## Stop

```bash
sudo pkill mjpg_streamer
```

## Access

- Web UI: `http://<hardware-host>:8080`
- Stream: `http://<hardware-host>:8080/?action=stream`
- Snapshot: `http://<hardware-host>:8080/?action=snapshot`

## Notes

- If the microscope is not detected after plugging in, reset the USB controllers on the hardware host:

  ```bash
  for bus in /sys/bus/usb/devices/usb*/authorized; do
    echo 0 | sudo tee "$bus" > /dev/null
    sleep 0.5
    echo 1 | sudo tee "$bus" > /dev/null
  done
  ```

- The prototype used a USB microscope exposed as a UVC `/dev/video*` device.
- Confirm supported resolution and frame rate with `v4l2-ctl --list-formats-ext`.
