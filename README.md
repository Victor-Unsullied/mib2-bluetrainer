# MIB2 Think Blue Trainer

**v0.2.0 is an offline preview for the reviewed Delphi 874B firmware, `MST2_EU_VW_P0635D` / MU `0757`.** It builds a candidate from the owner's matching HMI classes. The source contains no scoring thresholds, weights or history limits.

Think Blue starts with defaults from the firmware. A valid but entirely zero-filled 102-byte `EcoHmi` block can overwrite them. The overlay treats the known fields of that exact blank block as absent when the Trainer reads it, so the firmware keeps its original defaults. Nonblank configurations pass through unchanged. The Trainer continues to select its own scoring table and use the car's live signals. The Offroad and Trainer menu settings are separate from this repair.

## Choose a profile

| Builder option | Powertrain and gearbox detected by the firmware |
| --- | --- |
| `auto` | Any of the supported combinations below |
| `combustion-manual` | Combustion with a manual gearbox |
| `combustion-automatic` | Combustion with an automatic gearbox, including both Tiptronic states |
| `hybrid-manual` | Plug-in hybrid with a manual gearbox, if classified that way by the firmware |
| `hybrid-automatic` | Plug-in hybrid with an automatic gearbox, including both Tiptronic states |
| `electric` | Battery electric |

The selection is a compatibility check. When it differs from the native classification, the original `EcoHmi` response goes through unchanged. A plug-in hybrid uses the native combustion gearbox table and retains the firmware's hybrid history settings.

## Build offline

Use Python 3.10 or later and a Java runtime that can run Eclipse ECJ 4.6.1. Supply your local `ecj-4.6.1.jar`, `j9-foun11-classes.zip`, and the reviewed `MIBHMI-analysis.jar` converted from your firmware. The builder verifies the exact input hashes before compiling.

```text
python build_overlay.py --profile auto --compiler path/to/ecj-4.6.1.jar --bootclasses path/to/j9-foun11-classes.zip --hmi-api path/to/MIBHMI-analysis.jar --output thinkblue-overlay.jar
```

The resulting JAR contains the patched Trainer class derived from your firmware and two small helper classes. Keep that JAR and the firmware files local. The overlay needs to load before the built-in Trainer class. This preview does not install it, connect to a head unit or provide a vehicle rollback procedure. Native QNX/J9 loading and in-car scoring for this preview remain unverified.

The earlier R5 repair restored live scoring in a separate manual-transmission vehicle trial. The profile selection and blank-configuration behavior of this preview have been checked on a desktop JVM.

## Tests

```text
python -B -m unittest discover -s tests -v
```

For the optional desktop Java audit with your own reference JAR, see [tests/README.md](tests/README.md).

Use **Bug report** for offline tool problems or **Compatibility / support request** for firmware and vehicle questions. Include the project version, selected profile, head-unit model, Train and MU. Keep factory files, backups and identifiers private. [Open an issue](https://github.com/Victor-Unsullied/mib2-bluetrainer/issues/new/choose)
