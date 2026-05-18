# Tailscale Setup Guide

## What is Tailscale?

Tailscale is a mesh virtual private network (VPN) that allows you to securely connect multiple devices together from anywhere. Once you install Tailscale on your devices, they will all behave as if they are connected to the same Wi-Fi network.

ZotBins hosts most of its devices on a Tailscale network under the **ZotBins organization**. If you have Tailscale installed and are logged in with a GitHub account that is part of the ZotBins organization, you will automatically have access to the different devices on the network.

----------

## Prerequisites

-   A GitHub account registered under the ZotBins organization
-   A Linux-based terminal (for the commands below)

> **Note:** There are many tutorials available for setting up Tailscale on Windows as well. The steps below cover terminal-based setup.

----------

## Installation

### 1. Install Tailscale

Run the following command to install Tailscale on your device:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

### 2. Enable the Background Daemon

Once the package is installed, enable the `tailscaled` background service. After running this command, you will be prompted to log in — **use the GitHub account registered under the ZotBins organization** to gain access to ZotBins devices.

```bash
sudo systemctl enable --now tailscaled
```

----------

## Usage

### Turn Tailscale On

```bash
sudo tailscale up
```

### Turn Tailscale Off

```bash
sudo tailscale down
```

### Check Your Tailscale IP Address

Every device on the Tailnet has its own unique Tailscale IP address. To find yours:

```bash
tailscale ip
```

----------

## Connecting to Other Devices

Once you're on the same Tailnet, you can SSH into any other device using its Tailscale IP address just as you would on a local network:

```bash
ssh <tailscale-ip>
```

----------

## ZotBins Device Directory

Information about the devices on the ZotBins Tailnet can be found here:

[ZotBins Tailnet Device List](https://docs.google.com/document/d/1mCmLzgt0UxiaLB3Oio-9IXiDGniFGDwCs5cQMjZwDb0/edit?usp=sharing)
