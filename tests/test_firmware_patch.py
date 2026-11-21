import hashlib
import struct
import unittest
from unittest.mock import patch

from src import firmware
from src.classfile import ConstantPool, Reader, index_bytes


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def code_attribute(code, max_stack, max_locals):
    return struct.pack('>HHI', max_stack, max_locals, len(code)) + code + b'\x00' * 4


def fixture():
    pool = ConstantPool(Reader(index_bytes(1)))
    owner = pool.class_id(firmware.STOCK_CLASS)
    superclass = pool.class_id('java/lang/Object')
    int_type = pool.utf('I')
    fields = []
    for name in ('engineType', 'gearType'):
        field = pool.utf(name)
        pair = pool.add(12, index_bytes(field, int_type))
        fields.append(index_bytes(2, field, int_type, 0))
        pool.add(9, index_bytes(owner, pair))

    target = index_bytes(2, pool.utf('readDiagnosisData'), pool.utf(f'({firmware.ECO_HMI})V'), 1)
    other = index_bytes(1, pool.utf('unrelated'), pool.utf('()V'), 1)
    code_id = index_bytes(pool.utf('Code'))
    original_code = b'\x00' * 175 + b'\xb1'
    attribute = code_attribute(original_code, 4, 2)
    unrelated = code_attribute(b'\xb1', 0, 1)
    methods = (target + code_id + struct.pack('>I', len(attribute)) + attribute
               + other + code_id + struct.pack('>I', len(unrelated)) + unrelated)
    classfile = (b'\xca\xfe\xba\xbe\x00\x00\x00\x31' + pool.encode()
                 + index_bytes(0x0021, owner, superclass, 0, len(fields)) + b''.join(fields)
                 + index_bytes(2) + methods + index_bytes(0))
    return classfile, attribute


class FirmwarePatchTests(unittest.TestCase):
    def test_no_unknown_class_is_modified(self):
        original, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'Unrecognized stock Trainer class'):
            firmware.patch_firmware(original)

    def test_pinned_method_body_is_required(self):
        original, _ = fixture()
        with patch.object(firmware, 'STOCK_CLASS_SHA256', sha256(original)):
            with self.assertRaisesRegex(ValueError, 'diagnosis code SHA-256'):
                firmware.patch_firmware(original)

    def test_call_prefix_keeps_old_code_and_unrelated_members(self):
        original, attribute = fixture()
        with patch.object(firmware, 'STOCK_CLASS_SHA256', sha256(original)), patch.object(
            firmware, 'STOCK_CODE_SHA256', sha256(attribute)
        ):
            candidate = firmware.patch_firmware(original)

        self.assertEqual(candidate[:8], b'\xca\xfe\xba\xbe\x00\x00\x00\x30')
        self.assertEqual(candidate[-20:], original[-20:])
        reader = Reader(candidate)
        reader.take(8)
        pool = ConstantPool(reader)
        reader.take(6)  # access flags, this class and superclass
        self.assertEqual(reader.number(2), 0)  # interfaces
        reader.take(8 * reader.number(2))  # two fields with no attributes
        self.assertEqual(reader.number(2), 2)  # methods
        reader.take(10)  # first method header and code attribute name
        size = reader.number(4)
        new_attribute = reader.take(size)
        self.assertEqual(new_attribute[:8], struct.pack('>HHI', 4, 2, 192))
        self.assertEqual(new_attribute[24:], attribute[8:])
        prefix = new_attribute[8:24]
        self.assertEqual(prefix[:3], b'\x2b\x2a\xb4')
        self.assertEqual(prefix[5:7], b'\x2a\xb4')
        self.assertEqual(prefix[9], 0xB8)
        self.assertEqual(prefix[12:], b'\x4c\x00\x00\x00')
        method = pool.entries[int.from_bytes(prefix[10:12], 'big')]
        self.assertEqual(method[0], 10)
        owner, pair = struct.unpack('>HH', method[1:])
        self.assertTrue(firmware._is_class(pool, owner, firmware.HELPER_CLASS))
        name, descriptor = struct.unpack('>HH', pool.entries[pair][1:])
        self.assertTrue(pool.is_utf(name, 'preserve'))
        self.assertTrue(pool.is_utf(descriptor, f'({firmware.ECO_HMI}II){firmware.ECO_HMI}'))
