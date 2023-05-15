#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""ROS2 CSI Camera Image Publisher.
This script publishes csi camera image to a ROS2 topic in sensor_msgs.msg/Image format.
Example:
        $ colcon build --symlink-install
        $ ros2 launch camera_snap_shot camera_snap_shot.launch.py
"""

# ___Import Modules:
import os
import cv2
import json

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from ament_index_python.packages import get_package_share_directory
from std_msgs.msg import Bool
from cv_bridge import CvBridge

from . import PACKAGE_NAME


# ___Global Variables:
SETTINGS = os.path.join(
    get_package_share_directory("camera_capture"), "config/camera_capture_settings.json"
)
with open(SETTINGS) as fp:
    json_settings = json.load(fp)


# __Functions:
def gstreamer_pipeline(
    framerate: str = str(json_settings["framerate"]),
):
    return (
        "nvarguscamerasrc ! "
        "video/x-raw(memory:NVMM), "
        f"width=(int){1920}, height=(int){1080}, "
        f"format=(string)NV12, framerate=(fraction){framerate}/1 ! "
        "nvvidconv ! "
        "video/x-raw, format=(string)BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=(string)BGR ! "
        "appsink"
    )


# __Classes:
class CameraPublisher(Node):
    """this class captures immages from a CSI camera and publishes it as a livestream or snapshots to a topic"""

    def __init__(
        self,
        publish_livestream_topic: str,
        publish_snapshot_topic: str,
        snapshot_trigger_topic: str,
        livestream_state_topic: str,
    ):
        super().__init__(PACKAGE_NAME)

        # initialize publisher & subscirbers
        self.pub_cam_snapshot = self.create_publisher(Image, publish_snapshot_topic, 1)
        self.pub_cam_livestream = self.create_publisher(
            Image, publish_livestream_topic, 1
        )
        self.sub_cam_livestream_state = self.create_subscription(
            Bool, livestream_state_topic, self.start_livestream_callback, 1
        )
        self.sub_cam_snapshot_trigger = self.create_subscription(
            Bool, snapshot_trigger_topic, self.capture_snapshot_callback, 1
        )

        self.cap = cv2.VideoCapture(gstreamer_pipeline())
        self.bridge = CvBridge()
        self.image_location = f"{json_settings['image_location']}"
        self.image_counter = 0

    def start_livestream_callback(self, topic_msg: Bool):
        """This method starts a livestream when a message is received on the topic livestream/state

        Args:
        topic_msg (Bool): True for starting livestream, False for stopping livestream
        """
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, json_settings["capture_height_livestream"]
        )
        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH, json_settings["capture_width_livestream"]
        )

        self.get_logger().info(f"message received on topic livestream")
        self.get_logger().debug(
            f"Incoming message on topic livestream \nwith message: {topic_msg}"
        )
        timer_period = 0.03  # seconds TODO: make into settings 30hz
        if self.cap.isOpened():
            self.get_logger().info("camera is available")
            if topic_msg.data:
                self.get_logger().info("starting livestream")
                timer = self.create_timer(timer_period, self.timer_callback)
            elif not topic_msg.data:
                self.get_logger().info("stopping livestream")
                try:
                    timer.cancel()
                    timer.destroy()
                except UnboundLocalError:
                    self.get_logger().error("timer was is not defined)")
            else:
                self.get_logger().debug(
                    "can't stop livestream because livestream is already stopped"
                )
        else:
            self.get_logger().info("camera not available")

    def timer_callback(self):
        """callback function to read image data from camera and publish it to the topic of the livestream"""
        ret, frame = self.cap.read()
        msg_image = self.bridge.cv2_to_imgmsg(frame, "bgr8")
        self.pub_cam_livestream.publish(msg_image)

    def capture_snapshot_callback(self, topic_msg: Bool):
        """Captures images when a True is received on the snapshot topic and publishes the immage on a topic.

        Args:
            topic_msg (Bool): True for capturing snapshot, False is not used.
        """
        self.get_logger().info(
            f"message received on topic snapshot \nwith message: {topic_msg}\nwith data :{topic_msg.data}"
        )
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, json_settings["capture_height_snapshot"]
        )
        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH, json_settings["capture_width_snapshot"]
        )

        if self.cap.isOpened():
            ret, frame = self.cap.read()
            msg_image = self.bridge.cv2_to_imgmsg(frame, "bgr8")
            msg_image.header.frame_id = str(self.image_counter)
            cv2.imwrite(f"{self.image_location}/image{self.image_counter}.jpg", frame)
            self.get_logger().info(f"image saved at image{self.image_counter}.jpg")
            self.pub_cam_snapshot.publish(msg_image)
            self.image_counter += 1
            prevent_overflood_image(self.image_counter)
        else:
            self.get_logger().info("camera not available")
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, json_settings["capture_height_livestream"]
        )
        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH, json_settings["capture_width_livestream"]
        )


def prevent_overflood_image(img_number: int):
    """makes sure that there are only 5 images in the image folder

    Args:
        img_number (int): current number of latest image published
    """
    if img_number > 4:
        item_to_delete = f"{json_settings['image_location']}/image{img_number-5}.jpg"
        if os.path.exists(item_to_delete):
            os.remove(item_to_delete)


# ___Main Method:
def main(args=None):
    """
    This is the Main Method that spins the node and starts the camera publisher.
    """
    # initializes node and start publishing
    cam_0_base = json_settings["publish_topic_camera"] + json_settings["camera_id"]
    livestream_state_topic = (
        json_settings["publish_topic_livestream"]
        + json_settings["trigger_topic_livestream"]
    )
    snapshot_trigger_topic = (
        json_settings["publish_topic_snapshot"]
        + json_settings["trigger_topic_snapshot"]
    )
    publish_livestream_topic = json_settings["publish_topic_livestream"]
    publish_snapshot_topic = json_settings["publish_topic_snapshot"]
    rclpy.init(args=args)
    camera_0 = CameraPublisher(
        livestream_state_topic=cam_0_base + livestream_state_topic,
        snapshot_trigger_topic=cam_0_base + snapshot_trigger_topic,
        publish_livestream_topic=cam_0_base + publish_livestream_topic,
        publish_snapshot_topic=cam_0_base + publish_snapshot_topic,
    )
    rclpy.spin(camera_0)

    # shuts down nose and releases everything
    camera_0.destroy_node()
    rclpy.shutdown()

    return None


# ___Driver Program:
if __name__ == "__main__":
    main()
