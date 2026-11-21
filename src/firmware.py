"""Patch the diagnosis consumer in a locally supplied P0635D/MU0757 class."""

import hashlib
import struct

from .classfile import ConstantPool, Reader, index_bytes


STOCK_CLASS = 'de/vw/mib/asl/internal/car/thinkblue/ASLTargetThinkBlue'
STOCK_CLASS_ENTRY = STOCK_CLASS + '.class'
STOCK_CLASS_SHA256 = '77cd3e3ae0a4d4f5e67a06bb1a35c90c23131c5ff0198f738c1d95a326683330'
STOCK_CODE_SHA256 = '7c3bb34d9727192a8ca56ed6085ca6d15e8897e0b62da2d0e23f9e055d1e1e67'
ECO_HMI = 'Lde/vw/mib/asl/framework/api/diagnosis/config/EcoHmi;'
HELPER_CLASS = 'golf/thinkbluefix/FirmwareDefaults'


def _is_class(pool, index, name):
    entry = pool.entries[index]
    return entry[0] == 7 and pool.is_utf(int.from_bytes(entry[1:], 'big'), name)


def _field_reference(pool, name):
    for index, entry in enumerate(pool.entries):
        if not entry or entry[0] != 9:
            continue
        owner, pair = struct.unpack('>HH', entry[1:])
        if _is_class(pool, owner, STOCK_CLASS):
            field, descriptor = struct.unpack('>HH', pool.entries[pair][1:])
            if pool.is_utf(field, name) and pool.is_utf(descriptor, 'I'):
                return index
    raise ValueError(f'Missing original Trainer field reference: {name}')


def _patch_code(data, engine, gear, normalize):
    if hashlib.sha256(data).hexdigest() != STOCK_CODE_SHA256:
        raise ValueError('Unexpected original Trainer diagnosis code SHA-256')

    reader = Reader(data)
    stack, locals_count, length = struct.unpack('>HHI', reader.take(8))
    if (stack, locals_count, length) != (4, 2, 176):
        raise ValueError('Unexpected Trainer diagnosis stack, locals or code size')
    code = reader.take(length)
    if reader.take(4) != b'\x00\x00\x00\x00' or reader.pos != len(data):
        raise ValueError('Unexpected Trainer diagnosis code attributes')

    # Load the existing calibration and the native profile, then store only
    # the helper's result in the argument slot. Relative branch targets and
    # 4-byte switch alignment in the unchanged instructions remain valid.
    prefix = (b'\x2b\x2a\xb4' + index_bytes(engine) + b'\x2a\xb4' + index_bytes(gear)
              + b'\xb8' + index_bytes(normalize) + b'\x4c\x00\x00\x00')
    return struct.pack('>HHI', stack, locals_count, length + len(prefix)) + prefix + code + b'\x00' * 4


def patch_firmware(original: bytes) -> bytes:
    """Return a candidate for J9 offline review using the exact known class."""
    if hashlib.sha256(original).hexdigest() != STOCK_CLASS_SHA256:
        raise ValueError('Unrecognized stock Trainer class SHA-256')
    reader = Reader(original)
    if reader.take(8) != b'\xca\xfe\xba\xbe\x00\x00\x00\x31':
        raise ValueError('Unexpected original Trainer class version')
    pool = ConstantPool(reader)
    body_start = reader.pos
    reader.take(2)  # class access flags
    if not _is_class(pool, reader.number(2), STOCK_CLASS):
        raise ValueError('Unexpected original Trainer class name')
    engine = _field_reference(pool, 'engineType')
    gear = _field_reference(pool, 'gearType')
    helper = pool.class_id(HELPER_CLASS)
    signature = pool.add(12, index_bytes(pool.utf('preserve'), pool.utf(f'({ECO_HMI}II){ECO_HMI}')))
    normalize = pool.add(10, index_bytes(helper, signature))

    reader.take(2)  # superclass
    reader.take(2 * reader.number(2))  # interfaces
    for _ in range(reader.number(2)):  # fields
        reader.take(6)
        for _ in range(reader.number(2)):
            reader.take(2)
            reader.take(reader.number(4))

    replacements = []
    for _ in range(reader.number(2)):  # methods
        flags = reader.number(2)
        name = reader.number(2)
        descriptor = reader.number(2)
        attributes = reader.number(2)
        target = pool.is_utf(name, 'readDiagnosisData') and pool.is_utf(descriptor, f'({ECO_HMI})V')
        if target and (flags != 0x0002 or attributes != 1):
            raise ValueError('Unexpected Trainer diagnosis method flags or attributes')
        for _ in range(attributes):
            attribute = reader.number(2)
            start = reader.pos
            data = reader.take(reader.number(4))
            if target and pool.is_utf(attribute, 'Code'):
                code = _patch_code(data, engine, gear, normalize)
                replacements.append((start, reader.pos, struct.pack('>I', len(code)) + code))

    if len(replacements) != 1:
        raise ValueError('Expected exactly one stock Trainer diagnosis code attribute')
    start, end, replacement = replacements[0]
    # The analysis JAR uses version 49. Match the Java 1.4 class format
    # used by the historical overlay for the original J9 runtime.
    return original[:6] + index_bytes(48) + pool.encode() + original[body_start:start] + replacement + original[end:]
