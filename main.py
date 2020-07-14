#!/usr/bin/env python3
import os
import ssl
import re
import threading
import picamera
import time
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
import pantilthat

STATIC_PATH = "/static/"
STATIC_DIR = "static/"


class SplitFrames(object):
    def __init__(self):
        self.last_frame = None
        self.stream = io.BytesIO()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # Start of new frame; send the old one's length
            # then the data
            self.last_frame = self.stream.getvalue()
            # create a new stream to take the next load of data
            self.stream = io.BytesIO()
        self.stream.write(buf)


class Cam():
    def __init__(self):
        self.output = SplitFrames()
        self.recording = True
        self.thread = threading.Thread(target=self.thread_worker)
        self.thread.start()

    def get_frame(self):
        return self.output.last_frame

    def thread_worker(self):
        with picamera.PiCamera(resolution=(320, 240), framerate=10) as camera:
            camera.vflip = True
            camera.hflip = True
			
            time.sleep(2)
            camera.start_recording(self.output, format='mjpeg')
            while self.recording:
                camera.wait_recording(0.2)
            camera.stop_recording()

    def stop(self):
        self.recording = False

cam = Cam()

class RequestHandler(BaseHTTPRequestHandler):
    """This class deals with any HTTP requests and performs an appropriate action"""
    def handle_camera(self):
        """return a camera image as jpg"""
        self.send_response(200)
        self.send_header("Content-type", "image/jpeg")
        self.end_headers()
        self.wfile.write(cam.get_frame())

    def handle_pan_command(self):
        """manage a request to set pan/tilt values"""
        match = re.match(r"/pan\?pan=(.*)&tilt=(.*)", self.path)
        if match:
            try:
                pan = float(match.group(1))
                tilt = float(match.group(2))
            except ValueError:
                self.fail()
            else:
                if pan > 180:
                    pan -= 360
                if pan < -90:
                    pan = -85
                if pan > 90:
                    pan = 85

                print(f"PAN: {pan} {tilt}")
                self.send_html(bytes(f"<html><body>Pan: {pan}<br>Tilt: {tilt}</body></html>", encoding="utf-8"))

                pantilthat.pan(pan)
                pantilthat.tilt(tilt)

        else:
            self.fail()

    def handle_static(self, fname: str):
        """manage a request to get a static file"""
        fname = fname.replace("..", "") # avoid people trying to get files ooutside of the static dir
        fname = os.path.join(STATIC_DIR, fname)
        try:
            with open(fname, 'rb') as f:
                if fname.endswith("html"):
                    self.send_html(f.read())
                elif fname.endswith("png"):
                    self.send_png(f.read())
                else:
                    self.send_raw(f.read())
        except IOError:
            self.send_error(404, f"File not found: {fname}")

    def do_GET(self):
        print("GET: ", self.path)
        if self.path=="/":
            self.handle_static("index.html")
        elif self.path.startswith(STATIC_PATH):
            self.handle_static(self.path[len(STATIC_PATH):])
        elif self.path.startswith("/pan"):
            self.handle_pan_command()
        elif self.path.startswith("/cam"):
            self.handle_camera()

    def fail(self):
        self.send_error(400)

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html)

    def send_png(self, html):
        self.send_response(200)
        self.send_header("Content-type", "image/png")
        self.end_headers()
        self.wfile.write(html)

    def send_raw(self, html):
        self.send_response(200)
        self.send_header("Content-type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(html)

#create a HTTP server
httpd = HTTPServer(('0.0.0.0', 443), RequestHandler)

#convert socket to a SSL socket
#context  = ssl.create_default_context()
httpd.socket = ssl.wrap_socket(httpd.socket,
                               certfile="/home/pi/.ssh/server.crt",
                               keyfile="/home/pi/.ssh/server.key",
                               server_side=True)

#run the server
httpd.serve_forever()