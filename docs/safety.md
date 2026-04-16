# V2 Safety Model

The optical endstop signal is read from oscilloscope Channel 4.

| Voltage | Meaning | Action |
|---|---|---|
| `>= 4.5V` | clear | continue |
| `< 1.0V` | triggered | STOP |
| `1.0V-4.5V` | fault | STOP |
| unreadable | fault | STOP |

STOP means feed hold has been sent if possible and the current workflow must end. The operator must inspect and explicitly restart.
