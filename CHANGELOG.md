# Changelog

## v0.1.0 (First public installer prerelease)

- Prepare a Think Blue Trainer repair from matching owner-supplied head-unit files.
- Download and verify the compiler and converter as needed. The ZIP contains no firmware or calibration values.
- Offline checks passed. The preparation installer is untested on Windows and against a live head unit. In-car activation is pending.

## Earlier local development builds

### v0.4.1 (Guided preparation preview)

- Download and verify a compatible, fixed `jxe2jar` revision when conversion is needed.

### v0.4.0 (Guided preparation preview)

- Download and verify the Eclipse compiler when it is missing.
- Read the supported HMI and Java library files from an existing head-unit FTP service, or prepare them from a local backup.
- Verify converted HMI classes by content, independent of the JAR timestamps.

### v0.3.3 (Guided preparation preview)

- Show the D-Link DUB-E100 label check and save the head-unit IP in the local receipt. Offer `192.168.1.4` as the default.

### v0.3.2 (Guided preparation preview)

- Look beside the installer for reference files and ask for another folder only when a file is missing.

### v0.3.1 (Guided preparation preview)

- Explain the vehicle choices, local reference files, and save location in plain English and Turkish.
- Describe the scope of the local build and offer actionable messages for missing files and Java errors.

### v0.3.0 (Guided preparation preview)

- Add a Windows launcher and an English/Turkish wizard for profile selection, reference checks and private overlay preparation.
- Verify the prepared overlay against a local receipt and archive it on request.
- Vehicle activation and recovery remain pending validation of an early HMI loader.

### v0.2.0 (Offline preview)

- Keep the owner's firmware defaults when the native Trainer receives the reviewed blank EcoHmi configuration.
- Support automatic detection or an explicit powertrain and gearbox match, including both automatic gearbox modes.
- Build the overlay locally from the matching stock HMI classes. Remove embedded calibration values from the source.
- The new overlay is checked offline. Native loading and in-car results remain unverified.

### Earlier R5 prototype

- Prepared the R5 Think Blue Trainer repair and a local build tool that verifies the compiled classes.
- Added offline carrier composition for four reviewed Delphi profiles using owner-supplied archives.
- Verified the patched factory member against the historical factory digests and checked preservation of all unrelated members. Vehicle installation and recovery of this preview remain unverified.
- Added public bug and compatibility issue forms.
