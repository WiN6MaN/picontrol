# Hardware

Pi Control is a small add-on board for a Raspberry Pi inside a retro-console case. It provides a latching **power switch**, a **reset button**, a **power LED**, a **fan driver** and an **NFC reader** for game "cartridges".

This software targets the **Pi Control Rev 5** board on a **Raspberry Pi 3B** running **RetroPie 4.8**. Other Pi models share the same GPIO header and should work, but they are untested.

## What is on the board

| Part | Role |
|---|---|
| 16-pin header (2 × 8) | Connects to the first 16 pins of the Pi's 40-pin header |
| 4-pin front-panel connector (`LED`, `GND`, `PWR`, `RST`) | Power LED, latching power switch, momentary reset button |
| 2-pin fan connector + N-channel MOSFET, 10 kΩ resistor, 1N4001 flyback diode | Switches a fan from a GPIO |
| 6-pin NFC connector (`SCK`, `MISO`, `MOSI`, `SS`, `VCC`, `GND`) | PN532 NFC module (V3 board) |

The board design and its original software are by Evan Wright and Jared Kirchgatter; the case is a "Daft Mike" design. See the build notes that come with your kit for the bill of materials.

## Pin map

BCM numbers (what the software uses) and the matching physical pin on the Pi header:

| Function | BCM | Header pin | Direction | Notes |
|---|---|---|---|---|
| Power switch | 3 | 5 | input, pull-up | Closed to ground = **ON**. GPIO3 pulled low also wakes a halted Pi |
| Reset button | 23 | 16 | input, pull-up | Pressed = ground |
| LED | 14 | 8 | output | High = lit |
| Fan | 18 | 12 | output | Drives the MOSFET gate: high = fan on |
| NFC clock (SCLK) | 4 | 7 | output | Software SPI |
| NFC data in (MISO) | 17 | 11 | input | Software SPI |
| NFC data out (MOSI) | 27 | 13 | output | Software SPI |
| NFC chip select (SS) | 22 | 15 | output | Software SPI |

All eight pins fall within the first 16 header pins, which is exactly what the board's 16-pin connector carries.

> **Provenance.** These numbers were taken from the original Pi Control software, not from a schematic. If your board is wired differently, change them in the `[pins]` section of the configuration - nothing else needs to change. Always validate with `picontrol test` (below).

## Why software SPI?

The PN532 is wired to ordinary GPIO pins, not to the Pi's hardware SPI bus (GPIO 8-11). The SPI protocol is therefore generated in software (mode 0, least-significant bit first, as the PN532 requires). Consequences:

- You do **not** need to enable SPI in `raspi-config`.
- Transfers are slower than hardware SPI, which is irrelevant for reading a tag.

## The PN532 module

- Set the module's **mode switches to SPI before applying power** (the switches are read at power-up). On the common V3 board this is usually `S1 = OFF`, `S2 = ON`; check the silkscreen or the seller's manual for your module.
- Genuine PN532 V3 boards are recommended: the kit's author reports poor clones, which can cause intermittent failures.
- Supported tags: **MIFARE Classic 1K** (4-byte UID) with default keys, as shipped with the kit. NTAG and other tag types are not supported.

## Power switch, wake-up and LED

- The switch is a **latching** push button. Closing it connects GPIO3 to ground: that is what wakes a Pi that is halted after shutdown, and what the software reads as "ON". Opening it starts a graceful shutdown.
- The LED is driven directly from its GPIO by the software; it is lit while the service runs. It does **not** need the serial port. (Enabling the mini-UART with `enable_uart=1` is a common trick to light such an LED early, but on a Pi 3 it reportedly locks the core clock at 250 MHz, which can cost some graphics performance - so Pi Control avoids it.)
- The fan runs from the board's fan connector. Check the `+` / `-` marking and use a 5 V fan.

## Testing the wiring

Run these over SSH (the service does not need to be stopped for `nfc`; it yields the reader between polls):

```
picontrol test led        # the LED blinks 5 times
picontrol test fan        # the fan spins for 5 seconds
picontrol test buttons    # flip the power switch, press reset: states are printed live
picontrol test nfc        # finds the PN532, then shows the UID of a tag you present
```

If a test shows nothing, check the physical connection and the matching pin in `[pins]` with a multimeter before suspecting the software. See [troubleshooting](troubleshooting.md).
