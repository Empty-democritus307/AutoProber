# Bill of Materials

This BoM lists the hardware used or expected by the Autoprober prototype. Product availability changes, so the Amazon links below are search links, not pinned endorsements of a specific seller or ASIN. Verify dimensions, voltage, connector type, and return policy before buying.

## Core Hardware

| Category | Part | Notes | Amazon Search |
|---|---|---|---|
| Motion platform | Genmitsu 3018-PROVer V2 CNC Router, machine-only variant | GRBL-compatible CNC platform. The project expects USB serial control and working hard limits. | [Search](https://www.amazon.com/s?k=Genmitsu+3018-PROVer+V2+CNC+Router) |
| Vision | Plugable USB Digital Microscope, or similar lightweight UVC microscope | Tested class is a USB 2.0 UVC microscope exposed as `/dev/video0`, 1600x1200 snapshot capable. | [Search](https://www.amazon.com/s?k=Plugable+USB+Digital+Microscope) |
| Measurement and safety readout | Siglent SDS1104X-E oscilloscope | Used over LAN/SCPI. Channel 4 reads optical endstop voltage; Channel 1 is reserved for pogo measurement. | [Search](https://www.amazon.com/s?k=Siglent+SDS1104X-E) |
| Power control | UseeLink Matter smart power strip, or compatible controllable outlet strip | Used for lab outlet state/control. Dashboard support currently assumes Matter `chip-tool` behavior. | [Search](https://www.amazon.com/s?k=UseeLink+Matter+smart+power+strip) |
| Control host | Linux PC, mini PC, or laptop | Needs USB for CNC/microscope, LAN access to scope, Python runtime, and enough CPU for image capture/stitching. | [Search](https://www.amazon.com/s?k=linux+mini+pc+usb+ethernet) |

## Probe And Safety Assembly

| Category | Part | Notes | Amazon Search |
|---|---|---|---|
| Contact probe | Spring-loaded pogo pins with receptacles | Choose a tip shape and travel suitable for the target. Record dimensions before editing CAD. | [Search](https://www.amazon.com/s?k=spring+loaded+pogo+pin+receptacle) |
| Contact detection | 5V optical endstop module, G/S/V style | Powered from an external 5V supply. Output is read by oscilloscope Channel 4. Do not wire this into the CNC probe header. | [Search](https://www.amazon.com/s?k=5V+optical+endstop+module+G+S+V) |
| Compliance | Light compression spring | Provides controlled travel for the floating pogo carriage. Pen springs can work for prototypes; measure spring force before real boards. | [Search](https://www.amazon.com/s?k=small+compression+spring+assortment) |
| Pogo signal cable | BNC female to bare-wire RG316 pigtail | Carries pogo measurement path to oscilloscope Channel 1. Keep measurement path separate from contact detection. | [Search](https://www.amazon.com/s?k=BNC+female+to+bare+wire+RG316+pigtail) |
| Scope probes/leads | Oscilloscope probes and ground leads | C4 probe tip goes to optical endstop output; C4 ground clips to endstop ground. C1 is for pogo measurement. | [Search](https://www.amazon.com/s?k=oscilloscope+probe+10x+BNC) |
| Sensor power | 5V USB wall charger | Powers the optical endstop externally. Use a stable supply. | [Search](https://www.amazon.com/s?k=5V+USB+wall+charger) |
| Sensor power pigtail | USB to bare-wire power cable | Used to feed 5V/GND to the optical endstop from the USB charger. | [Search](https://www.amazon.com/s?k=USB+to+bare+wire+power+cable+5V) |

## Mechanical And Fixturing

| Category | Part | Notes | Amazon Search |
|---|---|---|---|
| Custom toolhead | Printed fixed mount, sliding carriage, and endstop tabs | Printable STL files are in `cad/`. Verify microscope diameter, pogo dimensions, endstop location, and CNC clearance before use. | Not purchased |
| 3D printer filament | PLA/PETG or suitable engineering filament | PETG or stronger material is preferable for parts under repeated stress. | [Search](https://www.amazon.com/s?k=PETG+filament+1.75mm) |
| Board fixture | PCB clamps, low-profile hold-downs, or fixture plate | Target must not shift during imaging or probing. Keep clamps out of the microscope/probe travel path. | [Search](https://www.amazon.com/s?k=CNC+PCB+clamps+hold+down) |
| Fasteners | M3 screw/nut/washer assortment | For printed mounts and fixture hardware. Confirm sizes against CAD before buying. | [Search](https://www.amazon.com/s?k=M3+screw+nut+washer+assortment) |
| Wires | Dupont jumper wires / silicone hookup wire | For low-voltage endstop wiring and prototype harnesses. Use strain relief. | [Search](https://www.amazon.com/s?k=dupont+jumper+wires+silicone+hookup+wire) |

## Non-Negotiable Wiring Notes

- The CNC probe header is not used for the optical endstop.
- The optical endstop is powered by an external 5V supply.
- The optical endstop output is read on oscilloscope Channel 4.
- Pogo measurement is separate and uses oscilloscope Channel 1.
- `Pn:P` in GRBL status is ignored.
- Any Channel 4 trigger or ambiguous voltage is a stop condition.

## Before Publishing Or Buying

- Replace generic search links with exact products only after verifying fit and electrical compatibility.
- Avoid affiliate links unless the project explicitly documents that policy.
- Add photos or diagrams of the final assembled hardware if releasing a build guide.
- Keep private target images and trial captures out of the release repository.
