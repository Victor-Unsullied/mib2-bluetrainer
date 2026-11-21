"""Guide a local Bluetrainer overlay build using the owner's matching files."""

import argparse
from datetime import datetime, timezone
from getpass import GetPassWarning, getpass
import hashlib
from ipaddress import IPv4Address
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import warnings
import zipfile

import build_overlay
from src import references as acquisition
from src.ethernet import wired_route


ROOT = Path(__file__).resolve().parent
DEFAULT_STATE = ROOT / 'private'
PROFILES = ('auto', *build_overlay.PROFILES)
OVERLAY = 'thinkblue-overlay.jar'
DEFAULT_HOST = IPv4Address('192.168.1.4')
PACKAGE_FILES = {'Install.cmd', 'build_overlay.py', 'install.py', 'src/classfile.py',
                 'src/ethernet.py', 'src/firmware.py', 'src/references.py',
                 'src/golf/thinkbluefix/FirmwareDefaults.java'}
PLAN = (
    '1. Choose your vehicle type, or let the head unit detect it.\n'
    '2. Check the D-Link DUB-E100 label and enter the head-unit IP.\n'
    '3. Use existing build files or read the two required files from your own unit.\n'
    '4. Review the details and prepare the repair file on this computer.\n'
    'Use --inspect to check the saved file or --rollback to move it to a local archive.\n'
    'Installing the repair in the car requires a tested way to load it at startup.',
    '1. Araç türünü seçin veya ünitenin otomatik olarak belirlemesini kullanın.\n'
    '2. D-Link DUB-E100 etiketini kontrol edin ve ünitenin IP adresini girin.\n'
    '3. Mevcut dosyaları kullanın veya gerekli iki dosyayı kendi ünitenizden okuyun.\n'
    '4. Bilgileri kontrol edin ve onarım dosyasını bu bilgisayarda hazırlayın.\n'
    'Kayıtlı dosyayı kontrol etmek için --inspect, arşivlemek için --rollback kullanın.\n'
    'Araçta kurulum için onarımın açılışta yüklenmesini sağlayan, denenmiş bir yöntem gerekir.',
)
PROFILE_LABELS = {
    'auto': ('Automatic detection', 'Otomatik algılama'),
    'combustion-manual': ('Petrol or diesel, manual gearbox', 'Benzinli veya dizel, manuel şanzıman'),
    'combustion-automatic': ('Petrol or diesel, automatic gearbox', 'Benzinli veya dizel, otomatik şanzıman'),
    'hybrid-manual': ('Plug-in hybrid, manual gearbox', 'Şarj edilebilir hibrit, manuel şanzıman'),
    'hybrid-automatic': ('Plug-in hybrid, automatic gearbox', 'Şarj edilebilir hibrit, otomatik şanzıman'),
    'electric': ('Battery electric', 'Tam elektrikli'),
}


def choose_language():
    value = input('Language / Dil [en/tr] (en): ').strip().lower() or 'en'
    if value not in ('en', 'tr'):
        raise ValueError('Choose en or tr / en veya tr seçin.')
    return value


def confirm(prompt, turkish):
    answer = input(prompt + (' [evet/Hayır]: ' if turkish else ' [yes/No]: ')).strip().lower()
    return answer in (('e', 'evet') if turkish else ('y', 'yes'))


def references(folder):
    tools = folder / 'build-tools'
    def tool(name):
        direct = folder / name
        return direct if direct.is_file() or not (tools / name).is_file() else tools / name
    return tool('ecj-4.6.1.jar'), tool('j9-foun11-classes.zip'), folder / 'MIBHMI-analysis.jar'


def check_references(folder, turkish=False):
    files = references(folder)
    for path in files:
        if not path.is_file():
            hint = 'Dosyanın bulunduğu klasörü seçin.' if turkish else 'Choose the folder that contains the required files.'
            raise ValueError(f'{path.name} {"bulunamadı." if turkish else "is missing."} {hint}')
    try:
        build_overlay.verify_references(*files)
    except ValueError as error:
        hint = ('Dosyaların bu kılavuzda belirtilen sürümlerini kullanın.' if turkish
                else 'Use the exact reference files listed in the guide.')
        raise ValueError(f'{error}. {hint}') from error
    return files


def converter_path(explicit, folder, cache, turkish):
    if explicit is not None:
        converter = explicit
    elif (folder / 'jxe-converter/jxe2jar.py').is_file():
        converter = folder / 'jxe-converter/jxe2jar.py'
    elif (ROOT / 'jxe-converter/jxe2jar.py').is_file():
        converter = ROOT / 'jxe-converter/jxe2jar.py'
    else:
        print('JXE dönüştürücü hazırlanıyor. Gerekirse doğrulanmış sürüm GitHub’dan indirilecek.' if turkish
              else 'Getting the JXE converter ready. If needed, the wizard will download the verified version from GitHub.', flush=True)
        try:
            return acquisition.converter_download(cache)
        except OSError as error:
            raise ValueError('The wizard could not download the JXE converter. Check your internet connection and try again.') from error
    if not converter.is_file():
        raise ValueError(f'jxe2jar.py could not be found at {converter}')
    return converter


def read_from_unit(host, temporary, turkish):
    print('Kendi ünitenizin kablolu bağlantısını ve mevcut FTP hesabını kullanın.' if turkish
          else 'Use the direct wired connection and the existing FTP login for your own head unit.')
    print('Yalnızca iki dosya okunur. FTP giriş bilgileri kablo üzerinden şifrelenmeden gönderilir.' if turkish
          else 'The wizard will read two files. FTP sends the login over the cable without encryption.')
    prompt = f'{host} adresindeki üniteden dosyalar okunsun mu?' if turkish else f'Read the two files from your head unit at {host}?'
    if not confirm(prompt, turkish):
        return None
    route = wired_route(host)
    if route is not None:
        name, source = route
        print(('Etkin Ethernet bağlantısı' if turkish else 'Active Ethernet connection') + f': {name} ({source})')
    else:
        source = None
    username = input('Ünitenin FTP kullanıcı adı: ' if turkish else 'Head-unit FTP username: ').strip()
    if not username or '\r' in username or '\n' in username:
        raise ValueError('Enter a valid existing head-unit FTP username.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', GetPassWarning)
        try:
            password = getpass('Ünitenin FTP şifresi: ' if turkish else 'Head-unit FTP password: ')
        except GetPassWarning as error:
            raise ValueError('Open an interactive terminal so the FTP password can be entered privately.') from error
    return acquisition.read_device(host, source, username, password, temporary)


def wizard_inputs(args, state, host, turkish):
    cache = state / 'references'
    folder = args.inputs or ROOT
    compiler, bootclasses, hmi_api = references(folder)
    if args.inputs is None:
        print(('Önce yükleyicinin bulunduğu klasöre bakılıyor' if turkish
               else 'Looking beside the installer first') + f': {folder}')
        _, cached_boot, cached_hmi = references(cache)
        if not (bootclasses.is_file() and hmi_api.is_file()) and cached_boot.is_file() and cached_hmi.is_file():
            bootclasses, hmi_api = cached_boot, cached_hmi

    if not (bootclasses.is_file() and hmi_api.is_file()):
        use_device = False
        raw_hmi = folder / 'MIBHMI.jxe'
        if not bootclasses.is_file() and (folder / 'classes.zip').is_file():
            bootclasses = folder / 'classes.zip'
        if args.inputs is None and not (bootclasses.is_file() and (hmi_api.is_file() or raw_hmi.is_file())):
            print('Onarımı oluşturmak için ünitenizin Java ve HMI dosyaları gerekli.' if turkish
                  else 'The repair needs the Java and HMI files from your own head unit.')
            print('  1. Kablolu bağlantı üzerinden üniteden oku\n  2. Bilgisayardaki dosyaları kullan' if turkish
                  else '  1. Read them from the head unit over the wired connection\n  2. Use files already on this computer')
            choice = input('Seçenek [Enter = iptal]: ' if turkish else 'Choose an option [Enter = cancel]: ').strip()
            if not choice:
                return None
            if choice not in ('1', '2'):
                raise ValueError('Choose option 1 or 2.')
            use_device = choice == '1'
            if not use_device:
                value = input('Dosyaların bulunduğu klasör: ' if turkish else 'Folder with your head-unit files: ').strip().strip('"')
                if not value:
                    return None
                folder = Path(value)
                compiler, bootclasses, hmi_api = references(folder)
                raw_hmi = folder / 'MIBHMI.jxe'
                if not bootclasses.is_file() and (folder / 'classes.zip').is_file():
                    bootclasses = folder / 'classes.zip'

        if use_device or not hmi_api.is_file():
            if not use_device and not (raw_hmi.is_file() and bootclasses.is_file()):
                raise ValueError('Choose a folder with MIBHMI.jxe and classes.zip, or supply both prepared head-unit files.')
            converter = converter_path(args.converter, folder, cache, turkish)
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.references-', dir=cache) as directory:
                temporary = Path(directory)
                if use_device:
                    inputs = read_from_unit(host, temporary, turkish)
                    if inputs is None:
                        return None
                    raw_hmi, bootclasses = inputs
                build_overlay.verify_file(bootclasses, build_overlay.REFERENCES['bootclasses'])
                print('HMI dosyası bu bilgisayarda hazırlanıyor…' if turkish else 'Preparing the HMI reference on this computer…', flush=True)
                converted = temporary / 'MIBHMI-analysis.jar'
                acquisition.convert_hmi(converter, raw_hmi, converted)
                hmi_api = cache / converted.name
                staged_boot = temporary / 'j9-foun11-classes.zip'
                if bootclasses != staged_boot:
                    shutil.copyfile(bootclasses, staged_boot)
                saved_boot = cache / staged_boot.name
                staged_boot.replace(saved_boot)
                converted.replace(hmi_api)
                bootclasses = saved_boot

    if not bootclasses.is_file():
        raise ValueError('The head-unit Java library is missing. Choose a folder with j9-foun11-classes.zip or classes.zip.')
    build_overlay.verify_file(bootclasses, build_overlay.REFERENCES['bootclasses'])
    build_overlay.read_verified_hmi(hmi_api)
    if not compiler.is_file():
        if not (cache / 'ecj-4.6.1.jar').is_file():
            print('Eclipse derleyicisi Maven Central üzerinden alınıyor…' if turkish
                  else 'Getting the Eclipse compiler from Maven Central…', flush=True)
        compiler = acquisition.compiler_download(cache)
    return compiler, bootclasses, hmi_api


def check_package():
    hashes = json.loads((ROOT / 'installer-manifest.json').read_text(encoding='utf-8'))['sha256']
    if not isinstance(hashes, dict) or set(hashes) != PACKAGE_FILES:
        raise ValueError('Installer file manifest is incomplete.')
    for name, expected in hashes.items():
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Installer file changed or is outside the package: {name}')


def inspect(prepared):
    receipt = json.loads((prepared / 'receipt.json').read_text(encoding='utf-8'))
    if (not isinstance(receipt, dict) or set(receipt) - {'head_unit_ip'} != {'profile', 'sha256'}
            or receipt['profile'] not in PROFILES):
        raise ValueError('Invalid preparation receipt.')
    if 'head_unit_ip' in receipt:
        IPv4Address(receipt['head_unit_ip'])
    with (prepared / OVERLAY).open('rb') as overlay:
        if hashlib.sha256(overlay.read()).hexdigest() != receipt['sha256']:
            raise ValueError('Prepared overlay does not match its receipt.')
    return receipt


def prepare(prepared, data, profile, host):
    prepared.parent.mkdir(parents=True, exist_ok=True)
    if prepared.exists() or prepared.is_symlink():
        raise ValueError('A preparation already exists. Inspect or retire it first.')
    receipt = {'profile': profile, 'sha256': hashlib.sha256(data).hexdigest(), 'head_unit_ip': str(host)}
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=prepared.parent) as staging:
        candidate = Path(staging) / 'prepared'
        candidate.mkdir()
        (candidate / OVERLAY).write_bytes(data)
        (candidate / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        inspect(candidate)
        candidate.rename(prepared)
    return receipt


def retire(prepared):
    inspect(prepared)
    label = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = prepared.with_name('retired-' + label)
    prepared.rename(destination)
    return destination


def guide(args, state, turkish):
    print('MIB2 Think Blue Trainer')
    print('Onarım dosyasını bu bilgisayarda hazırlayın.' if turkish
          else 'Prepare the repair file on this computer.')
    print('Araçta kurulum için onarımın açılışta yüklenmesini sağlayan, denenmiş bir yöntem gerekir.' if turkish
          else 'Installing the repair in the car requires a tested way to load it at startup.')
    prepared = state / 'prepared'
    if prepared.exists() or prepared.is_symlink():
        info = inspect(prepared)
        print(('Hazır dosya' if turkish else 'Repair file already prepared')
              + f": {prepared / OVERLAY} ({PROFILE_LABELS[info['profile']][turkish]})")
        print('Dosyayı kontrol etmek için --inspect, arşivlemek için --rollback kullanın.' if turkish
              else 'Use --inspect to check the file or --rollback to move it to a local archive.')
        return

    print('\n1. Araç türü' if turkish else '\n1. Vehicle type')
    profile = args.profile
    if profile is None:
        print('Emin değilseniz otomatik algılamayı seçin.' if turkish
              else 'Choose automatic detection if you are unsure.')
        print('Belirli bir tür seçerseniz onarım yalnızca ünite aynı türü algıladığında çalışır.' if turkish
              else 'If you choose a specific type, the repair will run only when the head unit detects that type.')
        options = {str(number): choice for number, choice in enumerate(PROFILES, start=1)}
        for number, choice in options.items():
            print(f'  {number}. {PROFILE_LABELS[choice][turkish]}')
        value = input('Seçenek [Enter = 1]: ' if turkish else 'Choose an option [Enter = 1]: ').strip() or '1'
        if value not in options:
            raise ValueError('Listeden bir seçenek numarası girin.' if turkish else 'Enter one of the option numbers shown.')
        profile = options[value]

    print('\n2. Ünite bağlantı bilgileri' if turkish else '\n2. Head-unit connection details')
    print('Araca bağlanmadan önce üniteye takılan adaptörün üzerinde D-Link DUB-E100 yazdığını kontrol edin.' if turkish
          else 'Before connecting to the car, check that the adapter plugged into the head unit is labeled D-Link DUB-E100.')
    host = args.host
    if host is None:
        print('Ünitenin servis menüsündeki adresi girin veya varsayılan adresi kaydetmek için Enter’a basın.' if turkish
              else 'Enter the IP shown in the head unit’s service menu, or press Enter to save the default.')
        address = input(f'Ünite IP adresi [Enter = {DEFAULT_HOST}]: ' if turkish
                        else f'Head-unit IP address [Enter = {DEFAULT_HOST}]: ').strip()
        try:
            host = IPv4Address(address) if address else DEFAULT_HOST
        except ValueError as error:
            raise ValueError('IP adresini noktalarla ayrılmış dört sayı olarak girin.' if turkish
                             else 'Enter the IP address as four numbers separated by dots.') from error

    print('\n3. Gerekli dosyalar' if turkish else '\n3. Files needed to build the repair')
    inputs = wizard_inputs(args, state, host, turkish)
    if inputs is None:
        print('Hazırlık iptal edildi.' if turkish else 'Preparation cancelled.')
        return
    compiler, bootclasses, hmi_api = inputs
    build_overlay.verify_references(*inputs)
    print('Dosyalar doğrulandı.' if turkish else 'The files match the supported version.')
    java = args.java
    if java is None:
        print('Bu bilgisayardaki Java’yı kullanmak için Enter’a basın. Gerekirse java.exe dosyasının tam yolunu girin.' if turkish
              else 'Press Enter to use Java already installed on this computer, or enter the full path to java.exe.')
        java = input('Java yolu [Enter = java]: ' if turkish else 'Java path [Enter = java]: ').strip().strip('"') or 'java'

    print('\n4. Kontrol edin ve onaylayın' if turkish else '\n4. Review and confirm')
    print(('Araç türü' if turkish else 'Vehicle type') + f': {PROFILE_LABELS[profile][turkish]}')
    print(('Daha sonra kullanılacak ünite IP adresi' if turkish else 'Head-unit IP for later use') + f': {host}')
    print(('Ünite yazılım dosyası' if turkish else 'Head-unit reference file') + f': {hmi_api.resolve()}')
    print(('Onarım dosyasının kaydedileceği yer' if turkish else 'Repair file will be saved to') + f': {prepared / OVERLAY}')
    if not confirm('Onarım dosyası bu bilgisayarda hazırlansın mı?' if turkish
                   else 'Prepare the repair file on this computer?', turkish):
        print('Hazırlık başlamadan iptal edildi.' if turkish else 'Cancelled before preparation.')
        return
    print('Onarım dosyası hazırlanıyor…' if turkish else 'Preparing the repair file…', flush=True)
    try:
        data = build_overlay.build(java, compiler, bootclasses, hmi_api, profile)
    except FileNotFoundError as error:
        if error.filename != java:
            raise
        raise ValueError('Java başlatılamadı. Yeniden çalıştırın ve java.exe dosyasının tam yolunu girin.' if turkish
                         else 'Java could not start. Run the wizard again and enter the full path to java.exe.') from error
    except subprocess.CalledProcessError as error:
        raise ValueError('Java onarım dosyasını oluşturamadı. Yukarıdaki hata mesajını kontrol edin.' if turkish
                         else 'Java could not build the repair file. Check the error message above.') from error
    receipt = prepare(prepared, data, profile, host)
    print(('Onarım dosyası hazır' if turkish else 'Repair file prepared') + f': {prepared / OVERLAY}')
    print(('Dosya özeti (SHA-256)' if turkish else 'File checksum (SHA-256)') + f": {receipt['sha256']}")
    print('Bu klasörü özel tutun. Bu adım yalnızca bilgisayarınızdaki hazırlığı tamamlar.' if turkish
          else 'Keep this folder private. This completes preparation on your computer.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check', action='store_true', help='Verify package files and optional local inputs')
    actions.add_argument('--plan', action='store_true', help='Show the offline preparation steps')
    actions.add_argument('--inspect', action='store_true', help='Verify the prepared local overlay')
    actions.add_argument('--rollback', action='store_true', help='Archive the prepared file on this computer')
    parser.add_argument('--language', choices=('en', 'tr'))
    parser.add_argument('--profile', choices=PROFILES)
    parser.add_argument('--inputs', type=Path, help='Folder containing prepared references or your extracted head-unit files')
    parser.add_argument('--converter', type=Path, help='Path to a compatible local jxe2jar.py converter')
    parser.add_argument('--java', help='Java executable or full path')
    parser.add_argument('--host', type=IPv4Address, help='Head-unit IPv4 address to record for later use')
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)

    turkish = args.language == 'tr'
    try:
        check_package()
        state = args.state_dir.resolve()
        prepared = state / 'prepared'
        if args.check:
            if args.inputs is not None:
                check_references(args.inputs, turkish)
            print('PASS: installer package and supplied references.' if args.inputs else 'PASS: installer package.')
        elif args.plan:
            print(PLAN[turkish])
        elif args.inspect:
            print(json.dumps(inspect(prepared), indent=2))
        else:
            turkish = (args.language or choose_language()) == 'tr'
            if args.rollback:
                if confirm('Hazırlanan dosya bu bilgisayarda arşivlensin mi?' if turkish
                           else 'Move the prepared file to an archive on this computer?', turkish):
                    print(('Arşiv klasörü' if turkish else 'Archive folder') + f': {retire(prepared)}')
            else:
                guide(args, state, turkish)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        status = 'Hazırlık durdu' if turkish else 'Preparation stopped'
        parser.exit(1, f'{status}: {error}\n')
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, '\nHazırlık iptal edildi.\n' if turkish else '\nPreparation cancelled.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
