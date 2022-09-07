import os
import storage_media

if __name__ == '__main__':
    devices = storage_media.MediaDevice.probe_media_devices()
    if len(devices) != 1:
        raise RuntimeError('uhhh, not sure what to do if there are more or less than one USB device')
    target_device = devices[0]
    if not target_device.is_mounted():
        target_device.mount_partition()
    foo_fname = os.path.join(target_device.media_path, 'foo.txt')
    with open(foo_fname, 'w') as fobj:
        fobj.write('hey, we wrote to the flash drive!\n')
        