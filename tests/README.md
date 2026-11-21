# Offline checks

The Python unit tests use a synthetic class and require no firmware files.

```text
python -B -m unittest discover -s tests -v
```

The optional audit uses the same local firmware and compiler inputs as the overlay builder, plus a desktop JDK with `java` and `javac`. It builds all six choices in a temporary directory and runs the original and patched Trainer configuration methods with fixture services. It compares settings with values initialized by the stock classes at runtime. It also checks that a nonblank payload, a different schema, and a mismatched profile pass through intact.

```text
python -B tests/audit_firmware.py --compiler path/to/ecj-4.6.1.jar --bootclasses path/to/j9-foun11-classes.zip --hmi-api path/to/MIBHMI-analysis.jar
```

Use `--java` and `--javac` for a JDK outside your command path. This audit checks a desktop JVM, independent of vehicle systems and the native QNX/J9 runtime.
