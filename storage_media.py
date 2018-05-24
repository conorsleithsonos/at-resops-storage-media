import os
import subprocess

from parse import *


#
# ----- StorageDeviceUsb -----
# Abstraction for data collected about a storage media device that is mounted from a USB device
# Uses the classes MediaDevice and Mountpoint since they have separate functions
#
# Multiple "StorageDeviceUsb" can be associated with a single medium (USB external hard drive)
# but will generally have a unique mountpoint (Unless an error occur on probing)
#
class StorageMediaUsb:
    media_device = None  # Will contain the media device associated with this USB storage media
    #  (May be shared among multiple multiple StorageMediaUsb objects)
    mountpoint = None  # Mount information associated with this storage media

    # Constructor
    def __init__(self, media_device, mountable):
        self.media_device = media_device
        self.mountpoint = mountable

    #  Returns the size in GB (human readable)
    def get_size_gb(self):
        return self.media_device.size / 1024 ** 3

    #  Print relevant field of this object in a cohesive parsable format
    def digest(self):
        return "mountpoint:{} partition:{} size_bytes:{} size_gb:{} format:{} model:{} vendor:{} device_name:{} block_path:{} media_path:{}".format(
            self.mountpoint.mountpoint, self.mountpoint.partition, self.media_device.size, self.get_size_gb(),
            self.mountpoint.fs_format, self.media_device.model, self.media_device.vendor, self.media_device.device_name,
            self.media_device.block_path, self.media_device.media_path)

    # Returns a list of all StorageMediaUsb objects connected to the system
    @staticmethod
    def probe_storage_media_usb_devices():
        mountable_list = Mountpoint.probe_mountpoints()
        media_device_list = MediaDevice.probe_media_devices()
        storage_media_usb_list = []

        # Multiple mountables can belong to same media device.
        # Individual objects of type StorageMediaUsb will be produced for same media device in that case.
        # This could be used to trigger a warning (Expecting only one mountpoint for each USB device connected)
        for mountable in mountable_list:
            matching_partition_list = [x for x in media_device_list if str(x.partition) == str(mountable.partition)]
            for matched_media_device in matching_partition_list:  # Multiple matches possible
                storage_media_usb_list.append(StorageMediaUsb(matched_media_device, mountable))

        return storage_media_usb_list


#
# ----- Mountpoint -----
#
# Helps abstract the parsed data from 'mount' command.
# Used as a helper class to build StorageMediaUsb objects.
#
class Mountpoint:
    partition = str()
    mountpoint = str()
    fs_format = str()
    details = str()

    def __init__(self, partition, mountpoint, fs_format, details):
        self.partition = partition
        self.mountpoint = mountpoint
        self.fs_format = fs_format
        self.details = details

    @staticmethod
    def probe_mountpoints():
        mount_output = str(subprocess.check_output(["mount"]), 'utf-8')
        mountpoint_list = []

        for line in mount_output.split('\n'):
            if line:
                parsed_mountpoint_info = parse("{} on {} type {} {}", line)
                mountpoint_list.append(
                    Mountpoint(parsed_mountpoint_info[0], parsed_mountpoint_info[1], parsed_mountpoint_info[2],
                               parsed_mountpoint_info[3]))

        return mountpoint_list


#
# ----- MediaDevice -----
# Helps abstract collected data about media devices. Used as a helper class to build StorageMediaUsb objects.
# This is not to be confused with the actual mountpoint(s) of this Media Device.
#
# Credit: Some code of the code in this module was created/inspired by Christian Vallentin <mail@vallentinsource.com>
# Repository: https://github.com/MrVallentin/mount.py
#
class MediaDevice:
    device = str()
    device_name = str()
    block_path = str()
    media_path = str()
    partition = str()
    removable = False
    size = str()
    model = str()
    vendor = str()

    def __init__(self, device):
        self.device = device
        self.device_name = os.path.basename(device)
        self.block_path = "/sys/block/%s" % self.device_name
        self.media_path = "/media/" + str(self.device_name)

        # Get partition
        fdisk_output = str(subprocess.check_output(["fdisk", "-l", str(device)]), 'utf-8')
        self.partition = fdisk_output.split("\n")[-2].split()[0].strip()

        # Find out if it is removable
        path_to_removable = self.block_path + "/removable"
        if os.path.exists(path_to_removable):
            with open(path_to_removable, "r") as f:
                self.removable = f.read().strip() == "1"
        else:
            self.removable = None

        # Get the number of sectors it takes and compute it as bytes
        path_to_size = self.block_path + "/size"
        if os.path.exists(path_to_size):
            with open(path_to_size, "r") as f:
                # Multiply by 512, as Linux sectors are always considered to be 512 bytes long
                # https://git.kernel.org/cgit/linux/kernel/git/torvalds/linux.git/tree/include/linux/types.h?id=v4.4-rc6#n121
                self.size = int(f.read().strip()) * 512
        else:
            self.size = None

        # Get vendor
        path_to_vendor = self.block_path + "/device/vendor"
        if os.path.exists(path_to_vendor):
            with open(path_to_vendor, "r") as f:
                self.vendor = f.read().strip()
        else:
            self.vendor = None

        # Get the model of the device
        path_to_model = self.block_path + "/device/model"
        if os.path.exists(path_to_model):
            with open(path_to_model, "r") as f:
                self.model = f.read().strip()
        else:
            self.model = None

    # Checks if device is mounted
    # Input: self
    # Output: True if mounted, False otherwise
    def is_mounted(self):
        return os.path.ismount(self.media_path)

    # Mounts device at location specified by self.partition
    # Input: self
    # Output: True if mounting worked, False otherwise
    def mount_partition(self):
        if not self.is_mounted():
            os.system("mkdir -p " + self.media_path)
            os.system("mount %s %s" % (self.partition, self.media_path))
            return self.is_mounted()

    # Unmounts device
    # Input: self
    # Output: True if unmounted successfully, False otherwise
    def unmount_partition(self):
        os.system("umount " + self.media_path)
        return not self.is_mounted()

    #
    # ----- probe_media_devices -----
    #
    # Static method that returns all media devices.
    # Use `$ sudo fdisk -l` and `$ sudo sfdisk -l /dev/sda` for more information.
    #
    # If the major number is 8, that indicates it to be a disk device.
    #
    # The minor number is the partitions on the same device:
    # - 0 means the entire disk
    # - 1 is the primary
    # - 2 is extended
    # - 5 is logical partitions
    # The maximum number of partitions is 15.
    #
    # Input: N/A (Static call to class function)
    #
    # Output: Returns a list of MediaDevice objects
    #
    @staticmethod
    def probe_media_devices():
        with open("/proc/partitions", "r") as f:
            devices = []

            for line in f.readlines()[2:]:  # skip header lines
                words = [word.strip() for word in line.split()]
                minor_number = int(words[1])
                device_name = words[3]

                if (minor_number % 16) == 0:
                    path = "/sys/class/block/" + device_name

                    if os.path.islink(path):
                        if os.path.realpath(path).find("/usb") > 0:
                            devices.append("/dev/" + device_name)

            # Get all media devices parsed and stored as objects
            media_devices_list = []
            for device in devices:
                if device:
                    media_devices_list.append(MediaDevice(device))

            return media_devices_list


if __name__ == '__main__':
    usb_storage_media = StorageMediaUsb.probe_storage_media_usb_devices()
    for device in usb_storage_media:
        if device:
            print(device.digest())
