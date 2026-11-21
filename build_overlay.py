#!/usr/bin/env python3
"""Build a local Think Blue Trainer overlay using the stock firmware's defaults."""

import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import zipfile

from src.firmware import STOCK_CLASS_ENTRY, patch_firmware


SOURCE = Path(__file__).resolve().parent / 'src/golf/thinkbluefix/FirmwareDefaults.java'
REFERENCES = {
    'compiler': '9cddda75f4a1b4469e73f44e7b61a3e897d0f657df4797f9106ffe88c4eeade0',
    'bootclasses': '02c425a49ff3e2b96751d2cd56462a01599ae0ec587c38f67ff13d4a4484ca8c',
    'hmi_api': 'fc96bb92ffe1d9212daa7c9b6fee05007434cf15525cd9ad7897dfe97ad4c956',
}
PROFILES = {
    'combustion-manual': ((1, 1),),
    'combustion-automatic': ((1, 2), (1, 3)),
    'hybrid-manual': ((3, 1),),
    'hybrid-automatic': ((3, 2), (3, 3)),
    'electric': ((4, 4),),
}
HELPER_ENTRIES = {
    'golf/thinkbluefix/FirmwareDefaults.class',
    'golf/thinkbluefix/SelectedProfile.class',
}


def profile_source(profile):
    pairs = [pair for group in PROFILES.values() for pair in group] if profile == 'auto' else PROFILES[profile]
    conditions = ' || '.join(f'(engineType == {engine} && gearType == {gear})' for engine, gear in pairs)
    return (
        'package golf.thinkbluefix;\n'
        'final class SelectedProfile {\n'
        '    private SelectedProfile() { }\n'
        '    static boolean matches(int engineType, int gearType) {\n'
        f'        return {conditions};\n'
        '    }\n'
        '}\n'
    )


def build(java, compiler, bootclasses, hmi_api, profile):
    profile_code = profile_source(profile)
    for key, path in (('compiler', compiler), ('bootclasses', bootclasses), ('hmi_api', hmi_api)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != REFERENCES[key]:
            raise ValueError(f'{path.name} SHA-256 is unfamiliar')
    with zipfile.ZipFile(hmi_api) as firmware:
        patched = patch_firmware(firmware.read(STOCK_CLASS_ENTRY))

    with tempfile.TemporaryDirectory(prefix='bluetrainer-') as temporary:
        root = Path(temporary)
        selected_profile = root / 'SelectedProfile.java'
        selected_profile.write_text(profile_code, encoding='ascii')
        classes = root / 'classes'
        classes.mkdir()
        subprocess.run([
            java, '-jar', str(compiler.resolve()), '-source', '1.4', '-target', '1.4',
            '-bootclasspath', str(bootclasses.resolve()), '-classpath', str(hmi_api.resolve()),
            '-d', str(classes), str(SOURCE), str(selected_profile),
        ], check=True, timeout=90)
        entries = {path.relative_to(classes).as_posix(): path.read_bytes()
                   for path in classes.rglob('*.class')}
    if entries.keys() != HELPER_ENTRIES or any(
        data[:8] != b'\xca\xfe\xba\xbe\x00\x00\x00\x30' for data in entries.values()
    ):
        raise ValueError('Unexpected Java 1.4 helper output')

    entries[STOCK_CLASS_ENTRY] = patched
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in sorted(entries.items()):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return output.getvalue()


def write_new_file(path, data):
    output = path.open('xb')
    try:
        with output:
            output.write(data)
    except OSError:
        path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('auto', *PROFILES), default='auto',
                        help='Expected powertrain and gearbox. Auto follows the firmware classification.')
    parser.add_argument('--java', default='java', help='Java executable or full path')
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--bootclasses', type=Path, required=True)
    parser.add_argument('--hmi-api', type=Path, required=True, help='Matching local MIBHMI-analysis.jar')
    parser.add_argument('--output', type=Path, help='New local JAR for offline verification')
    args = parser.parse_args()
    try:
        data = build(args.java, args.compiler, args.bootclasses, args.hmi_api, args.profile)
        if args.output is not None:
            write_new_file(args.output, data)
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        parser.exit(1, f'Overlay build failed: {error}\n')
    print(f'Built offline overlay for {args.profile}. SHA-256 {hashlib.sha256(data).hexdigest()}')
    if args.output is not None:
        print(f'Saved {args.output}')


if __name__ == '__main__':
    main()
